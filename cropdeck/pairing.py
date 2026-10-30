"""
Matching each front with its own back - by where the card lay on the platen, never by
list order.
"""

from __future__ import annotations

import numpy as np


def match_by_position(f_rects, b_rects, mirror: bool, width: int):
    """
    Pair each front with the back that came off the SAME SLOT on the platen.

    Index order is not trustworthy enough for this: it depends on a sort, and a sort
    can differ between two scans of the same layout. Physical position can't - the
    card was lying there. Returns (pairs, problem): pairs[i] is the index into
    b_rects for f_rects[i], or problem explains why it refused.
    """
    F = [(r[0][0], r[0][1]) for r in f_rects]
    B = [((width - r[0][0]) if mirror else r[0][0], r[0][1]) for r in b_rects]
    if len(F) != len(B):
        return None, f"{len(F)} front(s) vs {len(B)} back(s)"

    # how close two different slots ever get - half of that is a safe match radius
    spacing = min(
        (np.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(F) for b in F[i + 1 :]),
        default=None,
    )
    limit = spacing * 0.5 if spacing else float("inf")

    d = [[float(np.hypot(f[0] - b[0], f[1] - b[1])) for b in B] for f in F]
    pairs = [None] * len(F)
    used = set()
    order = sorted((d[i][j], i, j) for i in range(len(F)) for j in range(len(B)))
    for _dist, i, j in order:  # globally closest first
        if pairs[i] is None and j not in used:
            pairs[i], _ = j, used.add(j)
    worst = max(d[i][pairs[i]] for i in range(len(F)))
    if worst > limit:
        return None, (
            f"a card moved {worst / max(limit, 1) * 50:.0f}% of the way to a "
            f"neighbouring slot between the two scans - the layout doesn't "
            f"line up, so the pairing can't be trusted"
        )
    return pairs, None
