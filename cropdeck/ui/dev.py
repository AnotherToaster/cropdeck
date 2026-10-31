"""
Design-check helpers, only with `cropdeck ui --dev`: the components page shows every component in
every variant, to compare with the design's Components artboard.

Its card pictures are neutral shapes made here, as small SVG images: never real cards, and
nothing from tests/ (which is not part of the installed package). Wording and numbers are the
design's own samples.
"""

from __future__ import annotations

from urllib.parse import quote

# the design's sample card colours; a back is the same striped pattern on every card
FRONTS = ["#C2410C", "#0369A1", "#0E7490", "#4D7C0F", "#7C3AED", "#B45309", "#BE123C", "#334155"]
BACK = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 63 88'><defs><pattern id='p' width='7' "
    "height='7' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'><rect width='7' "
    "height='7' fill='#3A4552'/><rect width='3.5' height='7' fill='#46525F'/></pattern></defs>"
    "<rect width='63' height='88' fill='url(#p)'/></svg>"
)


def _uri(svg: str) -> str:
    return "data:image/svg+xml," + quote(svg)


def front(i: int) -> str:
    colour = FRONTS[i % len(FRONTS)]
    return _uri(
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 63 88'><rect width='63' height='88' "
        f"fill='{colour}'/><rect x='6' y='7' width='51' height='39' rx='2' fill='#fff' "
        f"fill-opacity='.24'/></svg>"
    )


def back() -> str:
    return _uri(BACK)


def sample() -> dict:
    """Everything the components page shows."""
    pairs = [{"number": f"{17 + i:03d}", "front": front(i), "back": back()} for i in range(8)]
    return {
        "pairs": pairs,
        "strip": [front(i) for i in range(8)],
        "segments": [
            {"fill": 1, "label": "Tray 1 · done"},
            {"fill": 1, "label": "Tray 2 · done"},
            {"fill": 1 / 8, "label": "Tray 3 · 1 of 8"},
            {"fill": 0, "label": "Tray 4"},
            {"fill": 0, "label": "Tray 5"},
        ],
    }
