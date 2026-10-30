"""
Sanity check: is the scan we are treating as "backs" actually backs?

The nightmare here is not a crash, it is a silent mispairing - you forget to scan
one tray's backs, every following tray shifts by one, and because card backs are
identical you cannot see it in the output. So we look: card backs are all the same
picture, card fronts are not. Measured on real scans, backs land ~11-26 against a
stored reference and fronts ~60-73, so the two are not close.
"""

from __future__ import annotations

import cv2
import numpy as np

from .detect import refine_rect
from .extract import extract_card

BACK_MATCH_LIMIT = 40.0  # vs a stored reference: above this, it isn't backs
BACK_UNIFORM_LIMIT = 26.0  # first tray, no reference yet: backs are this alike


def thumbs(img, rects, dpi, args, bg):
    out = []
    for r in rects:
        rr = r if args.no_refine else refine_rect(img, r, dpi, args.tolerance)
        c = extract_card(img, rr, dpi, 1.0, None, not args.no_upright, bg)
        out.append(cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), (48, 66)).astype(np.float32))
    return out


def self_diff(ts):
    if len(ts) < 2:
        return 0.0
    d = [float(np.abs(a - b).mean()) for i, a in enumerate(ts) for b in ts[i + 1 :]]
    return float(np.median(d))


def ref_diff(ts, ref):
    if ref is None or not ts:
        return None
    r = np.array(ref, dtype=np.float32)
    return float(np.median([np.abs(t - r).mean() for t in ts]))


def check_backs(f_th, b_th, ref):
    """Return None if the pair looks right, else a sentence explaining what's wrong."""
    fd, bd = ref_diff(f_th, ref), ref_diff(b_th, ref)
    if fd is not None and bd is not None:
        if bd > BACK_MATCH_LIMIT and fd > BACK_MATCH_LIMIT:
            return "neither scan looks like card backs - did you scan this tray's backs at all?"
        if fd < bd:
            return "these two look swapped - the FRONTS scan appears to hold the backs"
        return None
    # First tray ever, no reference to compare against. Fall back on the fact that
    # card backs are all the same picture: measured, backs score ~15 here and fronts
    # ~32-45, so anything above BACK_UNIFORM_LIMIT is not a scan of backs.
    sf, sb = self_diff(f_th), self_diff(b_th)
    if sb > BACK_UNIFORM_LIMIT:
        return (
            f"the second scan's cards don't look alike enough to be card backs "
            f"(scored {sb:.0f}, backs normally score under {BACK_UNIFORM_LIMIT:.0f}) "
            f"- is it really the backs?"
        )
    if sb > sf:
        return (
            "the second scan is less uniform than the first - backs should all "
            "look alike, so these may be swapped"
        )
    return None
