"""
Build the cropdeck wordmark: the icon (cropdeck/ui/static/img/icon.svg) followed by "cropdeck"
in Inter Bold.

The letters are written as outlines (SVG paths), so the logo renders the same everywhere -
on GitHub, in a browser without the font, in an image converter. Inter is under the SIL
Open Font License; it is downloaded when this runs and never committed.

    pip install fonttools
    python tools/wordmark.py            # writes logo-light.svg and logo-dark.svg next to the icon

"light" and "dark" mean the background the logo sits on.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from fonts import inter
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# the logo lives in the package, where the UI serves it; the README shows it from there too
ASSETS = Path(__file__).resolve().parent.parent / "cropdeck" / "ui" / "static" / "img"
TEXT_SIZE = 41.4  # font size in icon units: the lower-case letters sit level with the card
TEXT_X, BASELINE = 72, 46

# (word colour, accent colour) per background; the accent is the icon's teal
COLOURS = {"light": ("#1F2937", "#0F766E"), "dark": ("#F3F4F6", "#5EB8AE")}


def outline(font: TTFont, text: str, x: float, baseline: float) -> tuple[str, float]:
    """SVG path data for text set from (x, baseline); returns the path and the x where it ends."""
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = TEXT_SIZE / font["head"].unitsPerEm
    parts = []
    for ch in text:
        glyph = glyphs[cmap[ord(ch)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        parts.append(pen.getCommands())
        x += glyph.width * scale
    return " ".join(parts), x


def main():
    font = TTFont(io.BytesIO(inter(700)))
    icon = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", (ASSETS / "icon.svg").read_text().strip())
    crop, x = outline(font, "crop", TEXT_X, BASELINE)
    deck, x = outline(font, "deck", x, BASELINE)
    width = round(x + 6)
    for background, (word, accent) in COLOURS.items():
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 64">\n{icon}\n'
            f'<path fill="{word}" d="{crop}"/>\n<path fill="{accent}" d="{deck}"/>\n</svg>\n'
        )
        (ASSETS / f"logo-{background}.svg").write_text(svg)
        print(f"wrote {ASSETS / f'logo-{background}.svg'}")


if __name__ == "__main__":
    main()
