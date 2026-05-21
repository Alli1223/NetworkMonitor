"""Convert assets/icon.svg to a 256x256 PNG for the Linux AppImage.

Usage:
    python build/svg_to_png.py <output_path>
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: svg_to_png.py <output_path>", file=sys.stderr)
        return 2
    out = sys.argv[1]
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    svg_path = os.path.join(root, "assets", "icon.svg")
    if not os.path.exists(svg_path):
        print(f"ERROR: {svg_path} not found", file=sys.stderr)
        return 1
    try:
        from cairosvg import svg2png  # type: ignore
    except ImportError as exc:
        print(f"ERROR: missing dependency ({exc}). Install cairosvg.", file=sys.stderr)
        return 1
    svg2png(url=svg_path, write_to=out, output_width=256, output_height=256)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
