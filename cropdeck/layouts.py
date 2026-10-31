"""
How cards lie on the glass: the four layouts cropdeck knows, measured on an A4 glass (210 x 297 mm)
seen from above, top edge up.

This is the only table of them. The browser interface draws its glass pictures from it,
`cropdeck run` takes its default card count from it, and the tests lay their synthetic trays by it.
Their names and descriptions for people are texts (data/locales/ui), not here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .card import CARD_H_MM, CARD_W_MM

GLASS_W_MM, GLASS_H_MM = 210.0, 297.0


@dataclass(frozen=True)
class Layout:
    id: str
    sideways: bool  # cards turned 90 degrees, long side across
    xs: tuple[float, ...]  # left edge of each column, mm from the glass's left edge
    ys: tuple[float, ...]  # top edge of each row, mm from the glass's top edge

    @property
    def across(self) -> int:
        return len(self.xs)

    @property
    def down(self) -> int:
        return len(self.ys)

    @property
    def count(self) -> int:
        return self.across * self.down

    @property
    def card(self) -> tuple[float, float]:
        """Width and height of one card as it lies, in mm."""
        return (CARD_H_MM, CARD_W_MM) if self.sideways else (CARD_W_MM, CARD_H_MM)

    def slots(self) -> list[tuple[float, float]]:
        """Top-left corner of every card in counting order: left to right, top to bottom."""
        return [(x, y) for y in self.ys for x in self.xs]


# from the design handoff's table (docs/ui/HANDOFF.md, "Glass layouts")
LAYOUTS = {
    lay.id: lay
    for lay in (
        Layout("s8", sideways=True, xs=(12, 110), ys=(12, 83, 154, 225)),
        Layout("s6", sideways=True, xs=(12, 110), ys=(30, 117, 204)),
        Layout("u6", sideways=False, xs=(6, 73.5, 141), ys=(30, 130)),
        Layout("u9", sideways=False, xs=(6, 73.5, 141), ys=(6, 104, 202)),
    )
}
DEFAULT = "s8"
