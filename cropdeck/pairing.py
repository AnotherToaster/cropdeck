"""
Matching each front with its own back - by where the card lay on the platen, never by
list order.
"""

from __future__ import annotations

import numpy as np


def _centres(rects, mirror: bool = False, width: int = 0):
    return [((width - r[0][0]) if mirror else r[0][0], r[0][1]) for r in rects]


def _limit(points) -> float:
    """Half the distance between the two closest slots: a card nearer than that to a slot lies
    in it, a card farther away has moved toward a neighbour."""
    spacing = min(
        (np.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(points) for b in points[i + 1 :]),
        default=None,
    )
    return spacing * 0.5 if spacing else float("inf")


def _nearest(F, B):
    """Globally closest pairs first; returns (pairs, distances), pairs[i] an index into B."""
    d = [[float(np.hypot(f[0] - b[0], f[1] - b[1])) for b in B] for f in F]
    pairs: list[int | None] = [None] * len(F)
    used: set[int] = set()
    for _dist, i, j in sorted((d[i][j], i, j) for i in range(len(F)) for j in range(len(B))):
        if pairs[i] is None and j not in used:
            pairs[i] = j
            used.add(j)
    return pairs, d


def match_by_position(f_rects, b_rects, mirror: bool, width: int):
    """
    Pair each front with the back that came off the SAME SLOT on the platen.

    Index order is not trustworthy enough for this: it depends on a sort, and a sort
    can differ between two scans of the same layout. Physical position can't - the
    card was lying there. Returns (pairs, problem): pairs[i] is the index into
    b_rects for f_rects[i], or problem explains why it refused.
    """
    F, B = _centres(f_rects), _centres(b_rects, mirror, width)
    if len(F) != len(B):
        return None, f"{len(F)} front(s) vs {len(B)} back(s)"
    limit = _limit(F)
    pairs, d = _nearest(F, B)
    worst = max((d[i][pairs[i]] for i in range(len(F))), default=0.0)
    if worst > limit:
        return None, (
            f"a card moved {worst / max(limit, 1) * 50:.0f}% of the way to a "
            f"neighbouring slot between the two scans - the layout doesn't "
            f"line up, so the pairing can't be trusted"
        )
    return pairs, None


def moved_slots(f_rects, b_rects, mirror: bool, width: int) -> list[int]:
    """Indexes of the fronts whose back lies too far from their slot (the cards that moved)."""
    F, B = _centres(f_rects), _centres(b_rects, mirror, width)
    limit = _limit(F)
    pairs, d = _nearest(F, B)
    return [i for i, j in enumerate(pairs) if j is not None and d[i][j] > limit]


def match_slots(f_rects, b_rects, mirror: bool, width: int) -> list[int | None]:
    """
    Pair fronts and backs when their counts differ: pairs[i] is the back lying in front i's
    slot, or None when that slot has no back. A back is only taken from the front's own slot,
    never from a neighbour's, so a missing card leaves a gap instead of shifting the rest.
    """
    F, B = _centres(f_rects), _centres(b_rects, mirror, width)
    limit = _limit(F if len(F) >= len(B) else B)
    pairs, d = _nearest(F, B)
    return [j if j is not None and d[i][j] <= limit else None for i, j in enumerate(pairs)]
