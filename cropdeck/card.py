"""
Card geometry and scan resolution: the physical facts every other step measures against.
Thresholds elsewhere are in millimetres and converted through the dpi found here.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Card geometry. Standard trading card (Pokemon / MTG / Yu-Gi-Oh) = 63 x 88 mm.
# --------------------------------------------------------------------------
CARD_W_MM = 63.0
CARD_H_MM = 88.0
CARD_ASPECT = CARD_W_MM / CARD_H_MM  # 0.716


# --------------------------------------------------------------------------
# DPI detection
# --------------------------------------------------------------------------
def guess_dpi(img, stated_dpi: float | None) -> float:
    """If the user didn't say, infer DPI from the scan's short edge vs A4 width."""
    if stated_dpi:
        return float(stated_dpi)
    short_edge_px = min(img.shape[:2])
    a4_short_in = 210.0 / 25.4  # 8.268 in
    raw = short_edge_px / a4_short_in
    # snap to the nearest common scanner setting
    return min((75, 100, 150, 200, 300, 400, 600, 1200), key=lambda d: abs(d - raw))
