"""
What a guard-stop page shows (`/tray/{n}/stop`), worked out from the stop the run recorded: both
scans with the detected cards outlined, the fixes that fit this kind of stop, and the trays that
wait behind it.

Outlines: "matched" (teal) has its partner on the other scan, "suspicious" (amber) is the card
the stop is about, "missing" (dashed) marks a spot where the other scan has a card and this one
has none - or, for a card that moved, where it lay before.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .. import trays
from ..pairing import match_slots
from .i18n import t

# the fixes offered per kind of stop, primary first; every stop can also be skipped
FIXES = {
    "count": ("rescan", "pairs_only"),
    "notbacks": ("forgot", "new_back"),
    "swapped": ("swap", "keep"),
    "moved": ("rescan",),
    "unreadable": ("rescan",),
}


@dataclass
class Shape:
    points: str  # SVG polygon points, in the scan's own pixels
    kind: str  # matched, suspicious, missing
    label: str
    x: float  # where the label goes
    y: float


@dataclass
class Figure:
    side: str  # front or back: which scan of the tray
    file: str
    width: int
    height: int
    shapes: list[Shape] = field(default_factory=list)
    found: int = 0


@dataclass
class StopView:
    tray: trays.Tray
    kind: str
    detail: dict
    figures: list[Figure]
    fixes: tuple[str, ...]
    waiting: list[int]  # trays that run once this one is fixed or skipped

    @property
    def why(self) -> tuple[str, dict]:
        """The text key of the one-line reason, and its values."""
        d = self.detail
        if self.kind == "count":
            if d.get("missing"):
                return "stop.why.count_missing", {"spots": _listed(d["missing"])}
            return "stop.why.count_extra", {}
        if self.kind == "moved":
            return "stop.why.moved", {"spots": _listed(d.get("moved", []))}
        if self.kind in ("notbacks", "swapped"):
            return f"stop.why.{self.kind}", {}
        return "stop.why.unreadable", {"message": (self.tray.stop or {}).get("message", "")}

    @property
    def pairs(self) -> int:
        """Cards that have both sides (what "process with N pairs" writes)."""
        return self.detail.get("front_count", 0) - len(self.detail.get("missing", []))


def _shape(rect, kind: str, label: str, mirror_width: int | None = None) -> Shape:
    (cx, cy), (w, h), a = rect
    if mirror_width is not None:  # a front's spot, seen on a backs scan flipped as a block
        cx, a = mirror_width - cx, -a
    box = cv2.boxPoints(((cx, cy), (w, h), a))
    upper = box[np.argsort(box[:, 1])][:2]  # the two corners of the top edge ...
    top = upper[np.argmin(upper[:, 0])]  # ... and of those the left one
    points = " ".join(f"{x:.0f},{y:.0f}" for x, y in box)
    return Shape(points, kind, label, float(top[0]), float(top[1]))


def _listed(numbers) -> str:
    """7, 8 -> "7 and 8"; 3, 5, 6 -> "3, 5 and 6"."""
    words = [str(n) for n in numbers]
    if len(words) < 2:
        return "".join(words)
    return f"{', '.join(words[:-1])} {t('stop.and')} {words[-1]}"


def _rects(stored) -> list:
    """Rectangles as the state file keeps them, back in OpenCV's ((cx, cy), (w, h), angle)."""
    return [((r[0][0], r[0][1]), (r[1][0], r[1][1]), r[2]) for r in stored]


def build(tray: trays.Tray, folder: list[trays.Tray]) -> StopView:
    stop = tray.stop or {}
    kind, d = stop.get("kind", "unreadable"), stop.get("detail") or {}
    fronts, backs = d.get("fronts", []), d.get("backs", [])
    mirror = bool(d.get("mirror"))
    width = (d.get("size") or [0, 0])[0]
    figures = []
    if d.get("size") and d.get("back_size"):
        f_fig = Figure("front", tray.front.name, *d["size"], found=len(fronts))
        back_name = tray.back.name if tray.back else ""
        b_fig = Figure("back", back_name, *d["back_size"], found=len(backs))
        fr, br = _rects(fronts), _rects(backs)
        slots = match_slots(fr, br, mirror, width) if fr else []
        moved = set(d.get("moved", []))
        odd = kind in ("notbacks", "swapped")  # the stop is about the scan as a whole
        for i, r in enumerate(fr):
            n = i + 1
            f_kind = "suspicious" if odd or n in moved else "matched"
            f_fig.shapes.append(_shape(r, f_kind, str(n)))
            j = slots[i] if i < len(slots) else None
            if j is not None:
                b_fig.shapes.append(_shape(br[j], "suspicious" if odd else "matched", str(n)))
            else:  # no back in this card's spot: where it should be, dashed
                ghost = _shape(r, "missing", f"{n} ?", width if mirror else None)
                b_fig.shapes.append(ghost)
        used = {j for j in slots if j is not None}
        leftover = iter(sorted(moved))
        for j, r in enumerate(br):
            if j not in used:  # a back away from every front's spot: the card that moved
                b_fig.shapes.append(_shape(r, "suspicious", str(next(leftover, "?"))))
        figures = [f_fig, b_fig]

    after = [t.n for t in folder if t.n > tray.n and t.status not in (trays.DONE, trays.SKIPPED)]
    return StopView(tray, kind, d, figures, FIXES.get(kind, ("rescan",)), after)
