#!/usr/bin/env python3
"""DXF/DWG → spatial.yaml importer for SOMS.

Reads an AutoCAD DXF file (or DWG via ODA File Converter fallback),
extracts room polygons, associates text labels, and generates
config/spatial.yaml compatible with spatial_config.py.

Usage:
    # Step 1: Inspect layers
    python tools/import_floorplan.py "plan.dxf" --list-layers

    # Step 2: Extract with explicit layers
    python tools/import_floorplan.py "plan.dxf" \\
        --room-layer "A-AREA" --wall-layer "A-WALL" --text-layer "A-ANNO"

    # Step 3: Auto-detect from all closed polylines
    python tools/import_floorplan.py "plan.dxf" --auto

    # With SVG preview
    python tools/import_floorplan.py "plan.dxf" --auto --preview preview.svg
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
import yaml
from shapely.geometry import MultiLineString, Point, Polygon
from shapely.ops import polygonize


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Room:
    polygon: Polygon
    name: str = ""
    zone_id: str = ""
    floor: int = 1
    adjacent_zones: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_drawing(path: str) -> ezdxf.document.Drawing:
    """Load a DXF file. If path is .dwg, attempt ODA conversion first."""
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    if p.suffix.lower() == ".dwg":
        dxf_path = _convert_dwg_to_dxf(p)
        return ezdxf.readfile(str(dxf_path))

    return ezdxf.readfile(str(p))


def _convert_dwg_to_dxf(dwg_path: Path) -> Path:
    """Convert DWG to DXF using ODA File Converter."""
    oda = shutil.which("ODAFileConverter")
    if oda is None:
        # Check common install locations
        for candidate in [
            "/usr/bin/ODAFileConverter",
            "/opt/ODAFileConverter/ODAFileConverter",
            os.path.expanduser("~/ODAFileConverter/ODAFileConverter"),
        ]:
            if os.path.isfile(candidate):
                oda = candidate
                break

    if oda is None:
        print(
            "Error: ODA File Converter not found.\n"
            "  For .dwg files, either:\n"
            "  1. Install ODA File Converter (https://www.opendesign.com/guestfiles/oda_file_converter)\n"
            "  2. Export as .dxf from AutoCAD first",
            file=sys.stderr,
        )
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_dir = str(dwg_path.parent)
        output_dir = tmpdir
        # ODAFileConverter <input_dir> <output_dir> <output_version> <output_format>
        # ACAD2018 = AC1032, DXF format = 1
        cmd = [
            oda,
            input_dir,
            output_dir,
            "ACAD2018",  # output version
            "DXF",  # output type
            "0",  # recurse = no
            "1",  # audit = yes
            f"{dwg_path.name}",  # filter
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ODA conversion failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Find the output DXF
        dxf_name = dwg_path.stem + ".dxf"
        out_path = Path(output_dir) / dxf_name
        if not out_path.exists():
            # Try case-insensitive match
            for f in Path(output_dir).iterdir():
                if f.suffix.lower() == ".dxf":
                    out_path = f
                    break

        if not out_path.exists():
            print("Error: ODA conversion produced no output DXF", file=sys.stderr)
            sys.exit(1)

        # Copy to a persistent location next to the source
        dest = dwg_path.with_suffix(".dxf")
        shutil.copy2(str(out_path), str(dest))
        print(f"Converted {dwg_path.name} → {dest.name}")
        return dest


# ---------------------------------------------------------------------------
# Layer inspection
# ---------------------------------------------------------------------------

def list_layers(doc: ezdxf.document.Drawing) -> None:
    """Print a summary table of layers and entity counts."""
    msp = doc.modelspace()

    # layer_name -> {entity_type: count}
    stats: dict[str, Counter] = defaultdict(Counter)
    for entity in msp:
        layer = entity.dxf.layer
        stats[layer][entity.dxftype()] += 1

    # Collect all entity types for the header
    all_types = sorted({t for c in stats.values() for t in c})

    # Print header
    max_layer_len = max((len(l) for l in stats), default=10)
    max_layer_len = max(max_layer_len, 10)
    col_width = 10

    header = f"{'Layer':<{max_layer_len}}"
    for t in all_types:
        header += f"  {t:>{col_width}}"
    header += f"  {'TOTAL':>{col_width}}"
    print(header)
    print("-" * len(header))

    # Sort layers alphabetically
    for layer_name in sorted(stats.keys()):
        counts = stats[layer_name]
        row = f"{layer_name:<{max_layer_len}}"
        total = 0
        for t in all_types:
            c = counts.get(t, 0)
            total += c
            cell = str(c) if c > 0 else "."
            row += f"  {cell:>{col_width}}"
        row += f"  {total:>{col_width}}"
        print(row)

    print(f"\nTotal layers: {len(stats)}")
    print(f"Total entities: {sum(sum(c.values()) for c in stats.values())}")


# ---------------------------------------------------------------------------
# Polygon extraction
# ---------------------------------------------------------------------------

def extract_room_polygons(
    msp, layer: str, min_area: float = 1.0
) -> list[Polygon]:
    """Extract closed LWPOLYLINE entities from a layer as Shapely Polygons.

    Args:
        msp: ezdxf modelspace
        layer: layer name to filter
        min_area: minimum polygon area in drawing units² (filters noise)
    """
    polygons = []
    for entity in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
        if not entity.closed:
            continue
        pts = [(p[0], p[1]) for p in entity.get_points(format="xy")]
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if poly.is_valid and poly.area >= min_area:
            polygons.append(poly)

    # Also check for closed POLYLINE (2D) entities
    for entity in msp.query(f'POLYLINE[layer=="{layer}"]'):
        if not entity.is_closed:
            continue
        pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if poly.is_valid and poly.area >= min_area:
            polygons.append(poly)

    return polygons


def extract_all_closed_polylines(
    msp, min_area: float = 1.0
) -> list[Polygon]:
    """Extract closed polylines from ALL layers (for --auto mode)."""
    polygons = []
    for entity in msp:
        dtype = entity.dxftype()
        if dtype == "LWPOLYLINE" and entity.closed:
            pts = [(p[0], p[1]) for p in entity.get_points(format="xy")]
            if len(pts) >= 3:
                poly = Polygon(pts)
                if poly.is_valid and poly.area >= min_area:
                    polygons.append(poly)
        elif dtype == "POLYLINE" and entity.is_closed:
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if len(pts) >= 3:
                poly = Polygon(pts)
                if poly.is_valid and poly.area >= min_area:
                    polygons.append(poly)
    return polygons


def _collect_line_segments(msp, layer: str) -> list[tuple]:
    """Extract LINE and LWPOLYLINE segments from a single layer."""
    lines = []
    for entity in msp.query(f'LINE[layer=="{layer}"]'):
        start = entity.dxf.start
        end = entity.dxf.end
        lines.append(((start.x, start.y), (end.x, end.y)))

    for entity in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
        pts = [(p[0], p[1]) for p in entity.get_points(format="xy")]
        for i in range(len(pts) - 1):
            lines.append((pts[i], pts[i + 1]))
        if entity.closed and len(pts) >= 2:
            lines.append((pts[-1], pts[0]))
    return lines


def polygonize_walls(
    msp,
    layer: str,
    tolerance: float = 1.0,
    clip_bounds: Polygon | None = None,
) -> list[Polygon]:
    """Build room polygons from wall LINE/LWPOLYLINE segments using shapely.

    Supports comma-separated multiple layers (e.g. "G-LINE1,G-LINE2,D-PART").
    Uses buffer + boundary + polygonize to close door gaps.

    Args:
        msp: ezdxf modelspace
        layer: wall layer name(s), comma-separated
        tolerance: buffer distance in drawing units to close gaps (e.g. 250 for mm)
        clip_bounds: optional polygon to clip results to (e.g. from K-KEY)
    """
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    lines = []
    for lname in layer.split(","):
        lname = lname.strip()
        if lname:
            lines.extend(_collect_line_segments(msp, lname))

    if not lines:
        return []

    # Clip to bounds if provided
    if clip_bounds is not None:
        clipped = []
        for seg in lines:
            ls = LineString(seg)
            if clip_bounds.buffer(1000).intersects(ls):  # small margin
                clipped.append(ls)
        if not clipped:
            return []
        multi = unary_union(clipped)
    else:
        multi = MultiLineString(lines)

    # Buffer approach: buffer lines to close door gaps, then polygonize boundary
    if tolerance > 0:
        buffered = multi.buffer(tolerance)
        boundary = buffered.boundary
        if boundary.is_empty:
            return []
        result = list(polygonize(boundary))
    else:
        result = list(polygonize(multi))

    return [p for p in result if p.is_valid and p.area > 0]


# ---------------------------------------------------------------------------
# Text / room name association
# ---------------------------------------------------------------------------

def _get_text_entities(msp, layer: str | None = None) -> list[tuple[Point, str]]:
    """Extract TEXT and MTEXT entities as (point, text_content) pairs."""
    results = []
    query_filter = f'[layer=="{layer}"]' if layer else ""

    for entity in msp.query(f"TEXT{query_filter}"):
        insert = entity.dxf.insert
        pt = Point(insert.x, insert.y)
        text = entity.dxf.text.strip()
        if text:
            results.append((pt, text))

    for entity in msp.query(f"MTEXT{query_filter}"):
        insert = entity.dxf.insert
        pt = Point(insert.x, insert.y)
        # MTEXT can contain formatting codes; strip them
        text = entity.plain_text().strip()
        if text:
            results.append((pt, text))

    return results


def associate_room_names(
    polygons: list[Polygon],
    msp,
    text_layer: str | None = None,
) -> tuple[list[Room], list[tuple[Point, str]]]:
    """Match text labels to room polygons.

    Strategy:
    1. If text point is inside polygon → direct match
    2. If text point is inside buffered polygon → near match
    3. Otherwise → nearest polygon within a threshold

    Returns (rooms, unmatched_texts) where unmatched_texts are texts
    that could not be associated with any polygon.
    """
    texts = _get_text_entities(msp, text_layer)
    rooms: list[Room] = []

    # Filter out template/legend texts (far from main geometry)
    if polygons:
        from shapely.ops import unary_union
        all_bounds = unary_union(polygons).bounds
        center_y = (all_bounds[1] + all_bounds[3]) / 2
        height = all_bounds[3] - all_bounds[1]
        texts = [
            (pt, txt) for pt, txt in texts
            if abs(pt.y - center_y) < height * 2
        ]

    # Track which polygons have been named
    poly_names: dict[int, str] = {}
    matched_texts: set[int] = set()

    # Pass 1: contains match
    for ti, (pt, text) in enumerate(texts):
        for i, poly in enumerate(polygons):
            if poly.contains(pt):
                if i not in poly_names:
                    poly_names[i] = text
                    matched_texts.add(ti)
                break

    # Pass 2: buffered contains (catches texts near polygon edge)
    for ti, (pt, text) in enumerate(texts):
        if ti in matched_texts:
            continue
        for i, poly in enumerate(polygons):
            if i in poly_names:
                continue
            if poly.buffer(500).contains(pt):  # 500 drawing units margin
                poly_names[i] = text
                matched_texts.add(ti)
                break

    # Pass 3: nearest match for remaining texts
    unnamed_polys = [i for i in range(len(polygons)) if i not in poly_names]
    if unnamed_polys:
        for ti, (pt, text) in enumerate(texts):
            if ti in matched_texts:
                continue
            best_idx = None
            best_dist = float("inf")
            for i in unnamed_polys:
                dist = polygons[i].distance(pt)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
            threshold = _median_room_size(polygons) * 0.5
            if best_idx is not None and best_dist < threshold:
                poly_names[best_idx] = text
                matched_texts.add(ti)
                unnamed_polys.remove(best_idx)

    # Build Room objects
    for i, poly in enumerate(polygons):
        rooms.append(Room(
            polygon=poly,
            name=poly_names.get(i, ""),
        ))

    # Collect unmatched texts
    unmatched = [
        (pt, txt) for ti, (pt, txt) in enumerate(texts)
        if ti not in matched_texts
    ]

    return rooms, unmatched


def create_voronoi_rooms(
    unmatched_texts: list[tuple[Point, str]],
    boundary: Polygon,
    existing_rooms: list[Room],
) -> list[Room]:
    """Create approximate room polygons for texts that have no wall-derived polygon.

    Uses Voronoi-like partitioning: each text gets the area closest to it
    within the boundary, minus existing room polygons.
    """
    from shapely.ops import unary_union

    if not unmatched_texts or boundary.is_empty:
        return []

    # Subtract existing rooms from the boundary to get available space
    if existing_rooms:
        occupied = unary_union([r.polygon for r in existing_rooms])
        available = boundary.difference(occupied)
    else:
        available = boundary

    if available.is_empty:
        return []

    # For each unmatched text, create a room from the nearest available area
    rooms = []
    points = [(pt, txt) for pt, txt in unmatched_texts]

    # Simple approach: buffer each text point and intersect with available space
    # Use distance to nearest neighbor as approximate room radius
    for i, (pt, txt) in enumerate(points):
        # Find distance to nearest other text point
        min_dist = float("inf")
        for j, (other_pt, _) in enumerate(points):
            if i != j:
                d = pt.distance(other_pt)
                if d < min_dist:
                    min_dist = d
        # Also consider distance to existing rooms
        for r in existing_rooms:
            d = pt.distance(r.polygon.centroid)
            if d < min_dist:
                min_dist = d

        radius = min_dist * 0.6 if min_dist < float("inf") else 2000
        radius = max(radius, 500)  # minimum 500 drawing units

        room_poly = pt.buffer(radius, resolution=8).intersection(available)
        if room_poly.is_empty or room_poly.area < 1:
            continue

        # If result is MultiPolygon, take the largest piece
        if room_poly.geom_type == "MultiPolygon":
            room_poly = max(room_poly.geoms, key=lambda g: g.area)

        if room_poly.geom_type == "Polygon" and room_poly.area > 0:
            rooms.append(Room(polygon=room_poly, name=txt))

    return rooms


def _median_room_size(polygons: list[Polygon]) -> float:
    """Return median sqrt(area) of polygons as a scale reference."""
    if not polygons:
        return 1000.0
    sizes = sorted(math.sqrt(p.area) for p in polygons)
    return sizes[len(sizes) // 2]


# ---------------------------------------------------------------------------
# Coordinate normalization
# ---------------------------------------------------------------------------

def normalize_coordinates(
    rooms: list[Room],
    unit: str = "mm",
    simplify_tolerance: float = 0.1,
) -> tuple[list[Room], float, float]:
    """Shift coordinates so min corner is at origin, convert to meters, and simplify.

    Args:
        rooms: list of Room objects
        unit: drawing unit ("mm", "cm", "m")
        simplify_tolerance: simplification tolerance in meters (0 = no simplification)

    Returns (rooms, building_width_m, building_height_m).
    """
    scale = 1.0
    if unit == "mm":
        scale = 0.001
    elif unit == "cm":
        scale = 0.01
    elif unit == "m":
        scale = 1.0

    # Find bounding box across all rooms
    all_coords = []
    for room in rooms:
        all_coords.extend(room.polygon.exterior.coords)
    if not all_coords:
        return rooms, 0.0, 0.0

    min_x = min(c[0] for c in all_coords)
    min_y = min(c[1] for c in all_coords)
    max_x = max(c[0] for c in all_coords)
    max_y = max(c[1] for c in all_coords)

    normalized = []
    for room in rooms:
        coords = room.polygon.exterior.coords[:-1]  # drop closing duplicate
        new_coords = [
            ((x - min_x) * scale, (y - min_y) * scale)
            for x, y in coords
        ]
        new_poly = Polygon(new_coords)

        # Simplify polygon to reduce vertex count
        if simplify_tolerance > 0:
            simplified = new_poly.simplify(simplify_tolerance, preserve_topology=True)
            if simplified.is_valid and not simplified.is_empty:
                new_poly = simplified

        normalized.append(Room(
            polygon=new_poly,
            name=room.name,
            floor=room.floor,
        ))

    width_m = (max_x - min_x) * scale
    height_m = (max_y - min_y) * scale

    return normalized, width_m, height_m


# ---------------------------------------------------------------------------
# Adjacency detection
# ---------------------------------------------------------------------------

def detect_adjacency(
    rooms: list[Room], tolerance: float = 0.5
) -> list[Room]:
    """Detect adjacent zones using shapely buffer + intersects.

    Args:
        rooms: list of Room objects (must have zone_id set)
        tolerance: buffer distance in meters for adjacency test
    """
    for i, room_a in enumerate(rooms):
        adj = []
        buffered = room_a.polygon.buffer(tolerance)
        for j, room_b in enumerate(rooms):
            if i == j:
                continue
            if buffered.intersects(room_b.polygon):
                # Check they share a meaningful boundary (not just corner touch)
                shared = room_a.polygon.buffer(tolerance / 2).intersection(
                    room_b.polygon.buffer(tolerance / 2)
                )
                if shared.area > tolerance * tolerance:
                    adj.append(room_b.zone_id)
        room_a.adjacent_zones = adj
    return rooms


# ---------------------------------------------------------------------------
# Zone ID generation
# ---------------------------------------------------------------------------

_ZONE_ID_COUNTER: dict[str, int] = {}


def _make_zone_id(name: str) -> str:
    """Generate a snake_case zone ID from a room name."""
    if not name:
        idx = _ZONE_ID_COUNTER.get("room", 0) + 1
        _ZONE_ID_COUNTER["room"] = idx
        return f"room_{idx:02d}"

    # Try to create a meaningful ID
    # Remove common suffixes/prefixes for Japanese room names
    clean = name.strip()

    # For ASCII names, convert to snake_case
    if clean.isascii():
        zone_id = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()
        if not zone_id:
            zone_id = "room"
    else:
        # For Japanese names, use transliteration hints or generate an ID
        # Common Japanese room type mappings
        jp_map = {
            "会議室": "meeting_room",
            "キッチン": "kitchen",
            "トイレ": "toilet",
            "廊下": "hallway",
            "玄関": "entrance",
            "エントランス": "entrance",
            "受付": "reception",
            "倉庫": "storage",
            "サーバー": "server_room",
            "休憩": "break_room",
            "応接": "reception_room",
            "事務": "office",
            "作業": "workspace",
            "メイン": "main",
            "オフィス": "office",
            "ロビー": "lobby",
            "階段": "stairs",
            "エレベータ": "elevator",
            "給湯": "pantry",
            "更衣": "locker_room",
            "書庫": "archive",
            "印刷": "print_room",
            "通路": "corridor",
        }
        zone_id = None
        for jp, en in jp_map.items():
            if jp in clean:
                zone_id = en
                break
        if zone_id is None:
            zone_id = f"zone_{len(_ZONE_ID_COUNTER) + 1:02d}"

    # Ensure uniqueness
    base = zone_id
    counter = _ZONE_ID_COUNTER.get(base, 0)
    if counter > 0:
        zone_id = f"{base}_{counter}"
    _ZONE_ID_COUNTER[base] = counter + 1

    return zone_id


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------

def generate_spatial_yaml(
    rooms: list[Room],
    building_name: str,
    building_width: float,
    building_height: float,
    output: str,
) -> None:
    """Write spatial.yaml from extracted room data."""
    data: dict = {
        "building": {
            "name": building_name,
            "width_m": round(building_width, 1),
            "height_m": round(building_height, 1),
            "floor_plan_image": None,
        },
        "zones": {},
        "devices": {},
        "cameras": {},
    }

    for room in rooms:
        coords = list(room.polygon.exterior.coords)[:-1]  # drop closing point
        rounded = [[round(x, 2), round(y, 2)] for x, y in coords]
        area = round(room.polygon.area, 1)

        # Estimate grid dimensions from bounding box
        minx, miny, maxx, maxy = room.polygon.bounds
        w = maxx - minx
        h = maxy - miny
        grid_cols = max(1, round(w))
        grid_rows = max(1, round(h))

        zone_data = {
            "display_name": room.name or room.zone_id,
            "polygon": rounded,
            "area_m2": area,
            "floor": room.floor,
            "adjacent_zones": room.adjacent_zones,
            "grid_cols": grid_cols,
            "grid_rows": grid_rows,
        }
        data["zones"][room.zone_id] = zone_data

    # Write with nice formatting
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    # Custom representer for cleaner YAML output
    class FlowListDumper(yaml.SafeDumper):
        pass

    def _represent_list(dumper, data):
        # Use flow style for short numeric lists and coordinate pairs
        if all(isinstance(item, (int, float)) for item in data):
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True
            )
        if (
            all(isinstance(item, list) for item in data)
            and all(
                len(item) <= 4 and all(isinstance(v, (int, float)) for v in item)
                for item in data
            )
        ):
            # polygon coords — render each sub-list in flow style
            nodes = []
            for item in data:
                nodes.append(dumper.represent_sequence(
                    "tag:yaml.org,2002:seq", item, flow_style=True
                ))
            return yaml.SequenceNode(
                tag="tag:yaml.org,2002:seq", value=nodes
            )
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data)

    def _represent_none(dumper, _):
        return dumper.represent_scalar("tag:yaml.org,2002:null", "null")

    FlowListDumper.add_representer(list, _represent_list)
    FlowListDumper.add_representer(type(None), _represent_none)

    with open(output, "w") as f:
        yaml.dump(
            data,
            f,
            Dumper=FlowListDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    print(f"\nWritten: {output}")
    print(f"  Building: {building_name} ({building_width:.1f} x {building_height:.1f} m)")
    print(f"  Zones: {len(rooms)}")
    for room in rooms:
        adj = ", ".join(room.adjacent_zones) if room.adjacent_zones else "(none)"
        print(
            f"    {room.zone_id}: {room.name or '(unnamed)'}"
            f"  {room.polygon.area:.1f}m²  adj=[{adj}]"
        )


# ---------------------------------------------------------------------------
# SVG preview
# ---------------------------------------------------------------------------

def generate_svg_preview(
    rooms: list[Room],
    building_width: float,
    building_height: float,
    output: str,
) -> None:
    """Generate an SVG visualization of extracted rooms."""
    margin = 20
    scale = 50  # pixels per meter
    svg_w = building_width * scale + 2 * margin
    svg_h = building_height * scale + 2 * margin

    colors = [
        "#4FC3F7", "#81C784", "#FFB74D", "#E57373",
        "#BA68C8", "#4DB6AC", "#FFD54F", "#A1887F",
        "#90A4AE", "#F06292",
    ]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_w:.0f}" height="{svg_h:.0f}" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">',
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="#f5f5f5"/>',
    ]

    for i, room in enumerate(rooms):
        color = colors[i % len(colors)]
        coords = list(room.polygon.exterior.coords)
        # Flip Y axis (SVG has Y down, CAD has Y up)
        points = " ".join(
            f"{c[0] * scale + margin:.1f},{(building_height - c[1]) * scale + margin:.1f}"
            for c in coords
        )
        lines.append(
            f'<polygon points="{points}" '
            f'fill="{color}" fill-opacity="0.3" '
            f'stroke="{color}" stroke-width="2"/>'
        )

        # Label
        cx = room.polygon.centroid.x * scale + margin
        cy = (building_height - room.polygon.centroid.y) * scale + margin
        label = room.name or room.zone_id
        lines.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-family="sans-serif" font-size="12" fill="#333">'
            f'{label}</text>'
        )

    lines.append("</svg>")

    with open(output, "w") as f:
        f.write("\n".join(lines))
    print(f"SVG preview: {output}")


# ---------------------------------------------------------------------------
# Filter overlapping / nested polygons
# ---------------------------------------------------------------------------

def filter_room_polygons(
    polygons: list[Polygon],
    min_area_m2: float = 2.0,
    max_area_m2: float = 10000.0,
) -> list[Polygon]:
    """Filter polygons to likely room candidates.

    Removes:
    - Very small polygons (furniture, fixtures)
    - Very large polygons (building outline, site boundary)
    - Nested polygons (keep the innermost for overlapping pairs)
    """
    # Size filter
    candidates = [
        p for p in polygons
        if min_area_m2 <= p.area <= max_area_m2
    ]

    # Remove polygons that fully contain other candidates
    # (keep the smaller / innermost ones)
    result = []
    for i, p in enumerate(candidates):
        is_outer = False
        for j, q in enumerate(candidates):
            if i != j and p.contains(q) and q.area > min_area_m2:
                is_outer = True
                break
        if not is_outer:
            result.append(p)

    return result


# ---------------------------------------------------------------------------
# Main / CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import floor plan from DXF/DWG → spatial.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to .dxf or .dwg file")
    parser.add_argument(
        "--list-layers", action="store_true",
        help="List all layers and entity counts, then exit",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Auto-detect rooms from all closed polylines",
    )
    parser.add_argument("--room-layer", help="Layer containing room polygons (closed polylines)")
    parser.add_argument(
        "--wall-layer",
        help="Layer(s) containing wall lines, comma-separated (e.g. 'G-LINE1,G-LINE2,D-PART')",
    )
    parser.add_argument(
        "--clip-layer",
        help="Layer with closed polylines to use as clipping boundary (e.g. 'K-KEY')",
    )
    parser.add_argument("--text-layer", help="Layer containing room name labels")
    parser.add_argument(
        "--unit", default="mm", choices=["mm", "cm", "m"],
        help="Drawing unit (default: mm)",
    )
    parser.add_argument(
        "--output", "-o", default="config/spatial.yaml",
        help="Output YAML path (default: config/spatial.yaml)",
    )
    parser.add_argument(
        "--building-name", default="SOMS Office",
        help="Building name in output (default: SOMS Office)",
    )
    parser.add_argument(
        "--min-area", type=float, default=2.0,
        help="Minimum room area in m² (default: 2.0)",
    )
    parser.add_argument(
        "--max-area", type=float, default=10000.0,
        help="Maximum room area in m² (default: 10000.0)",
    )
    parser.add_argument(
        "--adjacency-tolerance", type=float, default=0.5,
        help="Adjacency detection buffer in meters (default: 0.5)",
    )
    parser.add_argument(
        "--wall-tolerance", type=float, default=250.0,
        help="Wall buffer tolerance in drawing units to close door gaps (default: 250 for mm)",
    )
    parser.add_argument(
        "--preview", metavar="SVG_PATH",
        help="Generate SVG preview of extracted rooms",
    )
    parser.add_argument(
        "--simplify", type=float, default=0.1,
        help="Polygon simplification tolerance in meters (default: 0.1, 0=disable)",
    )

    args = parser.parse_args()

    # Load drawing
    print(f"Loading: {args.input}")
    doc = load_drawing(args.input)
    msp = doc.modelspace()

    # Mode 1: list layers
    if args.list_layers:
        list_layers(doc)
        return

    # --- Resolve clip boundary ---
    clip_boundary = None
    if args.clip_layer:
        clip_polys = extract_room_polygons(msp, args.clip_layer, min_area=0)
        if clip_polys:
            from shapely.ops import unary_union
            clip_boundary = unary_union(clip_polys)
            print(f"Clip boundary from {args.clip_layer}: {len(clip_polys)} polygons, "
                  f"total {clip_boundary.area / 1e6:.0f}m²")

    # --- Extract room polygons (in original drawing units) ---
    orig_polygons: list[Polygon] = []

    if args.auto:
        print("Auto-detecting rooms from all closed polylines...")
        orig_polygons = extract_all_closed_polylines(msp)
        print(f"  Found {len(orig_polygons)} closed polylines")
    elif args.room_layer:
        print(f"Extracting rooms from layer: {args.room_layer}")
        orig_polygons = extract_room_polygons(msp, args.room_layer)
        print(f"  Found {len(orig_polygons)} closed polylines")

    if not orig_polygons and args.wall_layer:
        print(f"Building rooms from wall layers: {args.wall_layer}")
        orig_polygons = polygonize_walls(
            msp, args.wall_layer, args.wall_tolerance, clip_bounds=clip_boundary
        )
        print(f"  Built {len(orig_polygons)} polygons from walls")
    elif not orig_polygons and not args.auto and not args.room_layer:
        print(
            "Error: specify --auto, --room-layer, or --wall-layer\n"
            "  Use --list-layers first to inspect the drawing.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Associate text labels (in original coordinates) ---
    text_layer = args.text_layer
    rooms, unmatched_texts = associate_room_names(orig_polygons, msp, text_layer)

    # --- Create Voronoi rooms for unmatched texts ---
    if unmatched_texts and clip_boundary is not None:
        print(f"  {len(unmatched_texts)} texts unmatched, creating approximate rooms...")
        voronoi_rooms = create_voronoi_rooms(unmatched_texts, clip_boundary, rooms)
        rooms.extend(voronoi_rooms)
        print(f"  Created {len(voronoi_rooms)} approximate rooms")
    elif unmatched_texts:
        print(f"  Warning: {len(unmatched_texts)} texts unmatched (use --clip-layer for Voronoi fallback):")
        for pt, txt in unmatched_texts[:5]:
            print(f"    \"{txt}\"")

    if not rooms:
        print("Error: no room polygons found.", file=sys.stderr)
        sys.exit(1)

    # --- Normalize coordinates ---
    rooms, bw, bh = normalize_coordinates(rooms, args.unit, args.simplify)

    # --- Filter by area ---
    print(f"Filtering rooms (area {args.min_area}–{args.max_area} m²)...")
    filtered = []
    for room in rooms:
        if args.min_area <= room.polygon.area <= args.max_area:
            filtered.append(room)
    # Remove nested (keep innermost)
    result = []
    for i, r in enumerate(filtered):
        is_outer = False
        for j, q in enumerate(filtered):
            if i != j and r.polygon.contains(q.polygon) and q.polygon.area > args.min_area:
                is_outer = True
                break
        if not is_outer:
            result.append(r)
    rooms = result
    print(f"  {len(rooms)} rooms after filtering")

    if not rooms:
        print("Error: no rooms remain after filtering. Try adjusting --min-area / --max-area.", file=sys.stderr)
        sys.exit(1)

    # --- Generate zone IDs ---
    _ZONE_ID_COUNTER.clear()
    for room in rooms:
        room.zone_id = _make_zone_id(room.name)

    # --- Detect adjacency ---
    rooms = detect_adjacency(rooms, args.adjacency_tolerance)

    # --- Output ---
    generate_spatial_yaml(rooms, args.building_name, bw, bh, args.output)

    if args.preview:
        generate_svg_preview(rooms, bw, bh, args.preview)


if __name__ == "__main__":
    main()
