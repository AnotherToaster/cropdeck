"""Synthetic flatbed scans for the tests: abstract cards of true trading-card size, no card art.

Each card carries a small coloured square in its top-left corner, the same colour on its front
and its back. That mark is how the tests check pairing: a front and the back it was matched with
must carry the same colour. Backs are otherwise identical, as real card backs are.
"""

from __future__ import annotations

import cv2
import numpy as np

DPI = 300
MM = DPI / 25.4
CARD_W, CARD_H = round(63 * MM), round(88 * MM)
A4_W, A4_H = round(210 * MM), round(297 * MM)
# one distinct, saturated colour per slot (BGR)
MARKS = [
    (0, 0, 255),
    (0, 200, 0),
    (255, 0, 0),
    (0, 220, 220),
    (220, 0, 220),
    (220, 220, 0),
    (0, 120, 255),
    (128, 0, 128),
]
TILTS = (-2.5, 1.5, 3.0, -1.0, 0.5, -3.0, 2.0, -1.5)  # degrees, one per slot


def _front(i: int, rng) -> np.ndarray:
    """A colourful abstract front, different for every card."""
    img = np.full((CARD_H, CARD_W, 3), 40 + 30 * i, np.uint8)
    for _ in range(25):
        c = tuple(int(v) for v in rng.integers(30, 230, 3))
        x, y = int(rng.integers(0, CARD_W)), int(rng.integers(0, CARD_H))
        cv2.circle(img, (x, y), int(rng.integers(20, 120)), c, -1)
    cv2.rectangle(img, (0, 0), (CARD_W - 1, CARD_H - 1), (30, 200, 230), 18)  # yellow border
    return img


def _back() -> np.ndarray:
    """One back design shared by every card: dark blue with a light ellipse."""
    img = np.full((CARD_H, CARD_W, 3), (120, 40, 20), np.uint8)
    cv2.ellipse(
        img, (CARD_W // 2, CARD_H // 2), (CARD_W // 3, CARD_H // 4), 0, 0, 360, (200, 160, 60), -1
    )
    return img


def _mark(img: np.ndarray, i: int) -> np.ndarray:
    out = img.copy()
    s = round(8 * MM)
    cv2.rectangle(out, (30, 30), (30 + s, 30 + s), MARKS[i], -1)
    return out


def _slots(layout: str):
    """
    Card centres and angles on an A4 platen.

    "2x3": 2 columns x 3 rows of upright cards, ~1 cm apart.
    "4x2": 4 cards along the long side of the glass and 2 across, every card lying sideways
           (turned 90 degrees counter-clockwise) - the layout that fits 8 cards on A4.
    Every card also gets a small tilt of its own.
    """
    if layout == "2x3":
        cols, rows, w, h, base = 2, 3, CARD_W, CARD_H, 0.0
        gap_x = gap_y = round(12 * MM)
        x0, y0 = (A4_W - cols * w - gap_x) // 2, round(15 * MM)
    elif layout == "4x2":
        cols, rows, w, h, base = 2, 4, CARD_H, CARD_W, 90.0
        gap_x, gap_y = round(10 * MM), round(8 * MM)
        x0 = (A4_W - cols * w - (cols - 1) * gap_x) // 2
        y0 = (A4_H - rows * h - (rows - 1) * gap_y) // 2
    else:
        raise ValueError(f"unknown layout {layout!r}")
    for r in range(rows):
        for c in range(cols):
            yield (
                x0 + c * (w + gap_x) + w // 2,
                y0 + r * (h + gap_y) + h // 2,
                base + TILTS[r * cols + c],
            )


def _place(platen: np.ndarray, card: np.ndarray, cx: int, cy: int, angle: float):
    m = cv2.getRotationMatrix2D((CARD_W / 2, CARD_H / 2), angle, 1.0)
    m[0, 2] += cx - CARD_W / 2
    m[1, 2] += cy - CARD_H / 2
    warped = cv2.warpAffine(card, m, (platen.shape[1], platen.shape[0]))
    mask = cv2.warpAffine(
        np.full(card.shape[:2], 255, np.uint8), m, (platen.shape[1], platen.shape[0])
    )
    platen[mask > 127] = warped[mask > 127]


def tray(seed: int = 0, backing=(245, 245, 245), layout: str = "2x3"):
    """(fronts_scan, backs_scan, slot_colours): one tray of cards, fronts and backs."""
    rng = np.random.default_rng(seed)
    fronts = np.full((A4_H, A4_W, 3), backing, np.uint8)
    backs = fronts.copy()
    back = _back()
    for i, (cx, cy, a) in enumerate(_slots(layout)):
        tilt = a - round(a / 90) * 90
        _place(fronts, _mark(_front(i, rng), i), cx, cy, a)
        _place(backs, _mark(back, i), cx, cy, a - tilt * 1.5)  # flipped in place, re-tilted
    noise = rng.normal(0, 2, fronts.shape)
    return (
        np.clip(fronts + noise, 0, 255).astype(np.uint8),
        np.clip(backs + noise, 0, 255).astype(np.uint8),
        MARKS,
    )


def mark_colour(card: np.ndarray) -> tuple[int, int, int]:
    """The colour of a card image's corner mark (median of the mark area after cropping)."""
    s = round(8 * MM)
    pad = round(1 * MM)
    patch = card[pad + 30 + 5 : pad + 30 + s - 5, pad + 30 + 5 : pad + 30 + s - 5].reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))
