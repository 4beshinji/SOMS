#!/usr/bin/env python3
"""Generate printable ArUco marker images (DICT_4X4_50).

Usage:
    python edge/tools/generate_aruco.py              # IDs 0-7, 200mm
    python edge/tools/generate_aruco.py --ids 0 1 2  # specific IDs
    python edge/tools/generate_aruco.py --size 150    # 150mm markers
    python edge/tools/generate_aruco.py --output /tmp  # custom output dir

Output: PNG files sized for A4 printing (one marker per page with quiet zone).
"""
import argparse
from pathlib import Path

import cv2
import numpy as np


def generate_marker(
    marker_id: int,
    dict_name: str = "DICT_4X4_50",
    marker_size_mm: int = 200,
    dpi: int = 300,
    output_dir: Path = Path("aruco_markers"),
):
    """Generate a single ArUco marker PNG ready for A4 printing."""
    dict_id = getattr(cv2.aruco, dict_name)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)

    # Marker pixel size at target DPI
    marker_px = int(marker_size_mm / 25.4 * dpi)
    # Quiet zone: 25% of marker size on each side
    quiet_px = marker_px // 4

    # Generate marker image
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_px)

    # A4 page at target DPI (210mm x 297mm)
    page_w = int(210 / 25.4 * dpi)
    page_h = int(297 / 25.4 * dpi)

    # White page
    page = np.ones((page_h, page_w), dtype=np.uint8) * 255

    # Center marker on page
    total = marker_px + quiet_px * 2
    x_off = (page_w - total) // 2 + quiet_px
    y_off = (page_h - total) // 2 + quiet_px

    page[y_off : y_off + marker_px, x_off : x_off + marker_px] = marker_img

    # Label below marker
    label = f"ID:{marker_id}  {dict_name}  {marker_size_mm}mm"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = marker_px / 500
    thickness = max(1, int(scale * 2))
    (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
    tx = (page_w - tw) // 2
    ty = y_off + marker_px + quiet_px + th
    cv2.putText(page, label, (tx, ty), font, scale, 0, thickness, cv2.LINE_AA)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"aruco_{dict_name}_id{marker_id}_{marker_size_mm}mm.png"
    cv2.imwrite(str(path), page)
    print(f"  {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate ArUco markers for SOMS calibration")
    parser.add_argument("--ids", nargs="+", type=int, default=list(range(8)),
                        help="Marker IDs to generate (default: 0-7)")
    parser.add_argument("--size", type=int, default=200,
                        help="Marker size in mm (default: 200)")
    parser.add_argument("--dict", default="DICT_4X4_50",
                        help="ArUco dictionary (default: DICT_4X4_50)")
    parser.add_argument("--dpi", type=int, default=300,
                        help="Print resolution (default: 300)")
    parser.add_argument("--output", type=str, default="aruco_markers",
                        help="Output directory (default: aruco_markers/)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    print(f"Generating {len(args.ids)} markers ({args.size}mm, {args.dict}, {args.dpi}dpi)")

    for mid in args.ids:
        generate_marker(mid, args.dict, args.size, args.dpi, output_dir)

    print(f"\nDone. Print at 100% scale (no fit-to-page) on A4.")


if __name__ == "__main__":
    main()
