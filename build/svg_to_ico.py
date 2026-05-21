"""Convert assets/icon.svg to assets/icon.ico (Windows multi-resolution icon).

Used by the Windows build script. Requires cairosvg + Pillow.

Usage:
    python build/svg_to_ico.py
"""

from __future__ import annotations

import io
import os
import sys


def main() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    svg_path = os.path.join(root, "assets", "icon.svg")
    ico_path = os.path.join(root, "assets", "icon.ico")
    if not os.path.exists(svg_path):
        print(f"ERROR: {svg_path} not found", file=sys.stderr)
        return 1

    try:
        from cairosvg import svg2png  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:
        print(f"ERROR: missing dependency ({exc}). Install cairosvg and Pillow.",
              file=sys.stderr)
        return 1

    png_bytes = svg2png(url=svg_path, output_width=256, output_height=256)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, sizes=sizes)
    print(f"Wrote {ico_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
