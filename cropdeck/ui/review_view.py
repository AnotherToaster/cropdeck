"""
What the review shows (`/review`), worked out from cards.csv: every card with its fields and
how far along it is, in the order the chosen view asks for, a page at a time.

A card is "accepted" once the user said so, "unread" when recognition ran and read nothing,
"check" when what it read is a weak match the user has not typed over, and "filled" otherwise.
Recognition is off in the browser interface for now (handoff phase 6, v1 note): cards named by
`cropdeck name` show "check" and "unread", the rest start "filled" with empty fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .. import manifest, paths
from .thumbs import thumb_url

ACCEPTED, UNREAD, CHECK, FILLED = "accepted", "unread", "check", "filled"
NEEDS_LOOK = (UNREAD, CHECK)
FIELDS = ("name", "number", "set", "language", "variant")  # the columns the review edits
CHECK_BELOW = 0.9  # a name matched less closely than this is shown as "check"
SHOWS = ("look", "order", "accepted")  # "needs a look first", "card order", "accepted"
PER_PAGE = 40
_GROUP = {UNREAD: 0, CHECK: 0, FILLED: 1, ACCEPTED: 2}  # "needs a look first"


def status(row: dict) -> str:
    if row.get("accepted") == "yes":
        return ACCEPTED
    confidence = (row.get("confidence") or "").strip()
    if confidence == "-" and not row.get("name"):
        return UNREAD
    try:
        weak = float(confidence) < CHECK_BELOW
    except ValueError:
        weak = False
    return CHECK if weak and "name" not in manifest.typed(row) else FILLED


@dataclass
class Card:
    number: str  # as in cards.csv ("0019")
    status: str
    values: dict[str, str]
    front: str  # file names in sorted/
    back: str

    @property
    def unsure(self) -> set[str]:
        """Fields whose value recognition is not sure of."""
        return {"name"} if self.status == CHECK else set()

    @property
    def front_src(self) -> str:
        return thumb_url(self.front, large=True)

    @property
    def back_src(self) -> str:
        return thumb_url(self.back, large=True) if self.back else ""

    @property
    def full(self) -> tuple[str, str]:
        """The front and the back at full size, for the true-size view."""
        return tuple(f"/card/{quote(n)}" if n else "" for n in (self.front, self.back))


def card_of(row: dict) -> Card:
    return Card(
        row.get("card", ""),
        status(row),
        {k: row.get(k) or "" for k in FIELDS},
        row.get("front", ""),
        row.get("back", ""),
    )


def all_cards(folder: Path | None) -> list[Card]:
    if folder is None:
        return []
    rows = manifest.read(folder / paths.SORTED)
    return sorted((card_of(r) for r in rows if r.get("card") and r.get("front")), key=_number)


def _number(c: Card):
    return (int(c.number), "") if c.number.isdigit() else (0, c.number)


@dataclass
class Counts:
    total: int
    look: int  # unread or check
    filled: int  # filled in or accepted


def counts(cards: list[Card]) -> Counts:
    look = sum(c.status in NEEDS_LOOK for c in cards)
    return Counts(len(cards), look, len(cards) - look)


def needs_look(folder: Path | None) -> int:
    """The count on the Review nav item."""
    return counts(all_cards(folder)).look


@dataclass
class View:
    cards: list[Card]  # this page
    counts: Counts
    show: str
    page: int
    pages: int


def build(folder: Path | None, show: str = "look", page: int = 1) -> View:
    show = show if show in SHOWS else "look"
    cards = all_cards(folder)
    total = counts(cards)
    if show == "look":
        cards.sort(key=lambda c: _GROUP[c.status])  # stable: card order within each group
    elif show == "accepted":
        cards = [c for c in cards if c.status == ACCEPTED]
    pages = max(1, -(-len(cards) // PER_PAGE))
    page = min(max(1, page), pages)
    return View(cards[(page - 1) * PER_PAGE : page * PER_PAGE], total, show, page, pages)
