#!/usr/bin/env python3
"""DXF → spatial.yaml converter (prototype).

Usage:
    .venv/bin/python tools/dxf_to_spatial.py GITY_sample.dxf

Reads structural layer (C-STR) from DXF, classifies columns vs walls,
visualizes the layout, and attempts zone extraction.
"""

import sys
from pathlib import Path

import ezdxf
import yaml
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, box
from shapely.ops import polygonize, unary_union


def load_dxf(path: str, layer: str = "C-STR"):
    """Extract polylines from the specified layer."""
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    elements = []
    for e in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
        pts = [(p[0], p[1]) for p in e.get_points(format="xy")]
        elements.append({
            "points_mm": pts,
            "closed": e.closed,
            "num_points": len(pts),
        })
    return elements


def classify_elements(elements):
    """Classify structural elements into columns (4-pt rectangles) and walls."""
    columns = []
    walls = []
    for el in elements:
        poly = Polygon(el["points_mm"]) if el["closed"] and len(el["points_mm"]) >= 3 else None
        el["polygon"] = poly

        if el["closed"] and el["num_points"] == 4 and poly and poly.is_valid:
            # 4-point closed → likely a column
            bounds = poly.bounds  # (minx, miny, maxx, maxy)
            w = bounds[2] - bounds[0]
            h = bounds[3] - bounds[1]
            # Columns are roughly square-ish or small rectangles
            if max(w, h) < 2000:  # < 2m → column
                columns.append(el)
            else:
                walls.append(el)
        else:
            walls.append(el)

    return columns, walls


def mm_to_m(pts, origin_x, origin_y):
    """Convert mm coordinates to meters, offset by origin."""
    return [(round((x - origin_x) / 1000, 2), round((y - origin_y) / 1000, 2)) for x, y in pts]


def extract_bounding_box(elements):
    """Get the overall bounding box in mm."""
    all_x, all_y = [], []
    for el in elements:
        for x, y in el["points_mm"]:
            all_x.append(x)
            all_y.append(y)
    return min(all_x), min(all_y), max(all_x), max(all_y)


def attempt_zone_extraction(columns, walls, origin_x, origin_y, bldg_w, bldg_h):
    """Try to derive zones from wall geometry using polygonize.

    Strategy: collect all wall edges as lines, add building boundary,
    then use shapely.polygonize to find enclosed regions.
    """
    lines = []

    # Add building boundary
    bldg_box = box(origin_x, origin_y, origin_x + bldg_w * 1000, origin_y + bldg_h * 1000)
    lines.append(bldg_box.exterior)

    # Add wall outlines as lines
    for el in walls:
        pts = el["points_mm"]
        if el["closed"] and len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid:
                lines.append(poly.exterior)
        elif len(pts) >= 2:
            lines.append(LineString(pts))

    # Add column outlines
    for el in columns:
        poly = Polygon(el["points_mm"])
        if poly.is_valid:
            lines.append(poly.exterior)

    # Polygonize all lines
    all_lines = unary_union(MultiLineString([l for l in lines if l.length > 0]))
    regions = list(polygonize(all_lines))

    # Filter: remove very small regions (< 2 m²) and column-sized regions
    column_polys = []
    for el in columns:
        p = Polygon(el["points_mm"])
        if p.is_valid:
            column_polys.append(p)

    zones = []
    for region in regions:
        area_m2 = region.area / 1_000_000  # mm² → m²
        if area_m2 < 2.0:
            continue
        # Skip if region is basically a column
        is_column = False
        for cp in column_polys:
            if region.intersection(cp).area / region.area > 0.8:
                is_column = True
                break
        if is_column:
            continue
        zones.append(region)

    return zones


def generate_svg(elements, columns, walls, zones, origin_x, origin_y, bldg_w_mm, bldg_h_mm, output_path):
    """Generate an SVG visualization."""
    # SVG coordinate system: flip Y
    scale = 0.02  # mm → SVG units (1mm = 0.02 SVG px → 1m = 20px)
    padding = 20
    svg_w = bldg_w_mm * scale + 2 * padding
    svg_h = bldg_h_mm * scale + 2 * padding

    def tx(x):
        return (x - origin_x) * scale + padding

    def ty(y):
        return svg_h - ((y - origin_y) * scale + padding)

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" width="{svg_w:.0f}" height="{svg_h:.0f}">')
    parts.append(f'<rect width="{svg_w}" height="{svg_h}" fill="#fafafa"/>')

    # Draw zones (if any)
    colors = ["#e3f2fd", "#fce4ec", "#e8f5e9", "#fff3e0", "#f3e5f5",
              "#e0f7fa", "#fff9c4", "#fbe9e7", "#e8eaf6", "#f1f8e9"]
    for i, zone in enumerate(zones):
        coords = list(zone.exterior.coords)
        points_str = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in coords)
        color = colors[i % len(colors)]
        area_m2 = zone.area / 1_000_000
        cx, cy = zone.centroid.x, zone.centroid.y
        parts.append(f'<polygon points="{points_str}" fill="{color}" stroke="#90caf9" stroke-width="0.5" opacity="0.7"/>')
        parts.append(f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" font-size="4" text-anchor="middle" fill="#1565c0">zone_{i:02d} ({area_m2:.1f}m²)</text>')

    # Draw walls
    for el in walls:
        pts = el["points_mm"]
        if el["closed"] and len(pts) >= 3:
            points_str = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
            parts.append(f'<polygon points="{points_str}" fill="#455a64" stroke="#263238" stroke-width="0.3"/>')
        elif len(pts) >= 2:
            points_str = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
            parts.append(f'<polyline points="{points_str}" fill="none" stroke="#263238" stroke-width="0.5"/>')

    # Draw columns
    for el in columns:
        pts = el["points_mm"]
        points_str = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
        parts.append(f'<polygon points="{points_str}" fill="#b71c1c" stroke="#880e4f" stroke-width="0.3"/>')

    # Scale bar (5m)
    bar_x = padding
    bar_y = svg_h - 8
    bar_len = 5000 * scale  # 5m in SVG units
    parts.append(f'<line x1="{bar_x}" y1="{bar_y}" x2="{bar_x + bar_len}" y2="{bar_y}" stroke="#000" stroke-width="1"/>')
    parts.append(f'<text x="{bar_x + bar_len/2}" y="{bar_y - 2}" font-size="4" text-anchor="middle">5m</text>')

    parts.append("</svg>")

    Path(output_path).write_text("\n".join(parts))
    print(f"SVG saved: {output_path}")


def generate_spatial_yaml(zones, columns, origin_x, origin_y, bldg_w_mm, bldg_h_mm):
    """Generate spatial.yaml structure from extracted zones."""
    data = {
        "building": {
            "name": "GITY Office",
            "width_m": float(round(bldg_w_mm / 1000, 1)),
            "height_m": float(round(bldg_h_mm / 1000, 1)),
            "floor_plan_image": None,
        },
        "zones": {},
        "devices": {},
        "aruco_markers": {},
        "cameras": {},
    }

    for i, zone_poly in enumerate(zones):
        coords = list(zone_poly.exterior.coords)[:-1]  # drop closing point
        pts_m = [[float(round((x - origin_x) / 1000, 2)), float(round((y - origin_y) / 1000, 2))] for x, y in coords]
        area_m2 = float(round(zone_poly.area / 1_000_000, 1))

        # Estimate grid size
        bounds = zone_poly.bounds
        w = (bounds[2] - bounds[0]) / 1000
        h = (bounds[3] - bounds[1]) / 1000
        grid_cols = int(max(1, round(w / 1.5)))
        grid_rows = int(max(1, round(h / 1.5)))

        zone_id = f"zone_{i:02d}"
        data["zones"][zone_id] = {
            "display_name": zone_id,
            "polygon": pts_m,
            "area_m2": area_m2,
            "floor": 1,
            "adjacent_zones": [],
            "grid_cols": grid_cols,
            "grid_rows": grid_rows,
        }

    return data


def main():
    if len(sys.argv) < 2:
        print("Usage: dxf_to_spatial.py <input.dxf> [--output spatial.yaml]")
        sys.exit(1)

    dxf_path = sys.argv[1]
    output_yaml = None
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_yaml = sys.argv[i + 1]

    print(f"Reading: {dxf_path}")
    elements = load_dxf(dxf_path)
    print(f"Found {len(elements)} structural elements on C-STR layer")

    columns, walls = classify_elements(elements)
    print(f"Classified: {len(columns)} columns, {len(walls)} walls")

    min_x, min_y, max_x, max_y = extract_bounding_box(elements)
    bldg_w_mm = max_x - min_x
    bldg_h_mm = max_y - min_y
    print(f"Building: {bldg_w_mm/1000:.1f}m × {bldg_h_mm/1000:.1f}m")
    print(f"Origin: ({min_x:.0f}, {min_y:.0f}) mm")

    # Attempt zone extraction
    print("\nAttempting zone extraction via polygonize...")
    zones = attempt_zone_extraction(columns, walls, min_x, min_y, bldg_w_mm / 1000, bldg_h_mm / 1000)
    print(f"Extracted {len(zones)} candidate zones")
    for i, z in enumerate(zones):
        print(f"  zone_{i:02d}: {z.area/1_000_000:.1f} m²")

    # Generate SVG
    svg_path = Path(dxf_path).with_suffix(".svg")
    generate_svg(elements, columns, walls, zones, min_x, min_y, bldg_w_mm, bldg_h_mm, str(svg_path))

    # Generate YAML
    spatial = generate_spatial_yaml(zones, columns, min_x, min_y, bldg_w_mm, bldg_h_mm)
    if output_yaml:
        with open(output_yaml, "w") as f:
            yaml.dump(spatial, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"\nYAML saved: {output_yaml}")
    else:
        print("\n=== Generated spatial.yaml preview ===")
        print(yaml.dump(spatial, default_flow_style=False, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
