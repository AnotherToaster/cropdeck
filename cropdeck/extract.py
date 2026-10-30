"""
Cutting one card out of a scan at true scale: rotate, then crop a window of fixed size.
"""

from __future__ import annotations

import cv2

from .card import CARD_H_MM, CARD_W_MM


def extract_card(
    img,
    rect,
    dpi: float,
    pad_mm: float,
    out_dpi: float | None,
    upright: bool = True,
    bg_bgr=(0, 0, 0),
):
    """
    Deskew + crop one card, exactly to size.

    The corners are built in the rect's OWN rotated frame rather than sorted by image
    coordinates - sorting is ambiguous for a rotated box and silently rotates or
    squashes the result. The card is lifted in its native footprint (so nothing is
    ever stretched), then turned upright as a whole-image rotation.
    """
    (cx, cy), (rw, rh), angle = rect
    # minAreaRect reports a card tilted a little counter-clockwise as a landscape box at
    # ~87 deg; the fixed 90 deg clockwise turn below would then stand it up upside down
    # (found 29.10.2026 by the synthetic tests). Take the smallest rotation instead, so a
    # portrait card stays portrait and only a card that really lies sideways is turned.
    if angle > 45:
        angle -= 90
        rw, rh = rh, rw
    elif angle < -45:
        angle += 90
        rw, rh = rh, rw

    # ---- rotate, then crop. Nothing else. -------------------------------------
    # Stretching a detected box onto a nominal-size canvas would make every card's
    # scale depend on how accurate its detection was - which is exactly how a front
    # and its own back end up different widths. Instead: rotate the scan about the
    # card's centre (a rigid transform - no scaling, no distortion) and cut a window
    # of one fixed size out of it. Every card comes out at the same true scale, so a
    # detection that ran a hair wide shows up as a hair more background, never as a
    # squeezed card.
    long_px = int(round((CARD_H_MM + 2 * pad_mm) / 25.4 * dpi))
    short_px = int(round((CARD_W_MM + 2 * pad_mm) / 25.4 * dpi))
    dst_w, dst_h = (long_px, short_px) if rw >= rh else (short_px, long_px)

    M = cv2.getRotationMatrix2D((float(cx), float(cy)), angle, 1.0)  # scale locked at 1.0
    M[0, 2] += dst_w / 2.0 - cx  # re-centre the card in the output window
    M[1, 2] += dst_h / 2.0 - cy
    # anything outside the scan is filled with the backing colour, not smeared edge
    # pixels - a card sitting near the platen edge would otherwise grow a fake border
    card = cv2.warpAffine(
        img,
        M,
        (dst_w, dst_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=[float(v) for v in bg_bgr],
    )

    # only now, if asked, change resolution - uniformly, both axes together
    if out_dpi and abs(out_dpi - dpi) > 1e-6:
        f = out_dpi / dpi
        card = cv2.resize(
            card, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC
        )

    # stand it up: a sideways card becomes portrait (use --rotate 180 if it lands upside down)
    if upright and card.shape[1] > card.shape[0]:
        card = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE)
    return card
