"""
Draw the installed app window's icons (192 and 512 px PNG) from the cropdeck icon.

    pip install cairosvg
    python tools/pwa_icons.py       # writes cropdeck/ui/static/img/icon-192.png and icon-512.png
"""

from pathlib import Path

import cairosvg

IMG = Path(__file__).resolve().parent.parent / "cropdeck" / "ui" / "static" / "img"

for size in (192, 512):
    out = IMG / f"icon-{size}.png"
    cairosvg.svg2png(
        url=str(IMG / "icon.svg"), write_to=str(out), output_width=size, output_height=size
    )
    print(f"wrote {out}")
