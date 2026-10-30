"""
Build the README picture: two raw scans on the left, what `cropdeck split --pair` makes of them
on the right. The cards are drawn here - original, deliberately generic designs, no trading-card
game's art or colours - and laid on a synthetic A4 platen by tests/synth.py. The right-hand side
is real cropdeck output, not a mock-up.

    pip install pillow
    python tools/demo_image.py      # writes docs/assets/demo-light.png and demo-dark.png
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fonts import inter
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import synth  # noqa: E402

from cropdeck.cli import main as cropdeck  # noqa: E402

ASSETS = ROOT / "docs" / "assets"
SS = 2  # draw cards at twice the size, then shrink: smooth edges without antialiasing support

# one hue per card (RGB), the rest of each card is neutral
HUES = [
    (46, 134, 171),
    (214, 104, 83),
    (94, 160, 98),
    (155, 105, 190),
    (222, 160, 52),
    (70, 90, 160),
    (196, 82, 128),
    (128, 136, 62),
]

THEMES = {  # background, panel, text, muted text, arrow
    "light": ((255, 255, 255), (246, 247, 249), (31, 41, 55), (107, 114, 128), (245, 158, 11)),
    "dark": ((13, 17, 23), (22, 27, 34), (243, 244, 246), (156, 163, 175), (245, 158, 11)),
}


def _canvas():
    w, h = synth.CARD_W * SS, synth.CARD_H * SS
    img = Image.new("RGB", (w, h))
    return img, ImageDraw.Draw(img), w, h


def _finish(img) -> np.ndarray:
    img = img.resize((synth.CARD_W, synth.CARD_H), Image.LANCZOS)
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def front(i: int, rng) -> np.ndarray:
    """A generic collectible card: dark frame, title bar, an abstract landscape, text lines."""
    hue = HUES[i % len(HUES)]
    img, d, w, h = _canvas()
    m = int(w * 0.045)
    d.rectangle([0, 0, w, h], fill=(38, 40, 46))
    d.rounded_rectangle([m, m, w - m, h - m], radius=m, fill=(236, 236, 232))
    d.rounded_rectangle([2 * m, 2 * m, w - 2 * m, 2 * m + h // 14], radius=m // 2, fill=hue)
    d.ellipse([w - 2 * m - h // 14, 2 * m, w - 2 * m, 2 * m + h // 14], fill=(250, 250, 250))
    top, bottom = 2 * m + h // 14 + m, int(h * 0.56)
    sky = [tuple(min(255, int(c + (255 - c) * 0.55)) for c in hue), hue]
    for y in range(top, bottom):  # a vertical gradient for the sky
        t = (y - top) / (bottom - top)
        colour = tuple(int(a + (b - a) * t) for a, b in zip(*sky, strict=True))
        d.line([(2 * m, y), (w - 2 * m, y)], fill=colour)
    sun = int(rng.integers(w // 4, 3 * w // 4))
    d.ellipse(
        [sun - w // 10, top + h // 20, sun + w // 10, top + h // 20 + w // 5], fill=(253, 236, 180)
    )
    peaks = (
        [(2 * m, bottom)]
        + [
            (int(x), int(rng.integers(top + (bottom - top) // 3, bottom - m)))
            for x in np.linspace(2 * m, w - 2 * m, 6)
        ]
        + [(w - 2 * m, bottom)]
    )
    d.polygon(peaks, fill=tuple(int(c * 0.55) for c in hue))
    for k, frac in enumerate((0.84, 0.66, 0.78, 0.5)):
        y = bottom + m + k * (h // 16)
        d.rounded_rectangle(
            [2 * m, y, 2 * m + int((w - 4 * m) * frac), y + h // 40],
            radius=h // 80,
            fill=(170, 172, 176),
        )
    d.rounded_rectangle([2 * m, h - 3 * m - h // 40, w // 3, h - 3 * m], radius=h // 80, fill=hue)
    return _finish(img)


def back() -> np.ndarray:
    """One back for every card: deep teal with the cropdeck crop marks."""
    img, d, w, h = _canvas()
    teal, light, amber = (15, 118, 110), (94, 184, 174), (245, 158, 11)
    m = int(w * 0.045)
    d.rectangle([0, 0, w, h], fill=(38, 40, 46))
    d.rounded_rectangle([m, m, w - m, h - m], radius=m, fill=teal)
    d.rounded_rectangle([3 * m, 3 * m, w - 3 * m, h - 3 * m], radius=m, outline=light, width=m // 2)
    cx, cy, s, t = w // 2, h // 2, w // 5, m // 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * s, cy + sy * s
            d.line([(x, y), (x - sx * s // 2, y)], fill=amber, width=t)
            d.line([(x, y), (x, y - sy * s // 2)], fill=amber, width=t)
    return _finish(img)


def cut_tray() -> tuple[np.ndarray, np.ndarray, list[tuple[np.ndarray, np.ndarray]]]:
    """A synthetic tray, run through the real split step. Returns both scans and the pairs."""
    fronts, backs, _ = synth.tray(seed=7, layout="s8", front=front, back=back(), marked=False)
    with tempfile.TemporaryDirectory() as tmp:
        scans, out = Path(tmp, "scans"), Path(tmp, "sorted")
        scans.mkdir()
        cv2.imwrite(str(scans / "scan_0001.png"), fronts)
        cv2.imwrite(str(scans / "scan_0002.png"), backs)
        argv = ["split", str(scans), "-o", str(out), "--pair", "--expect", "8"]
        if cropdeck(argv + ["--dpi", str(synth.DPI), "--no-sheet"]) != 0:
            raise SystemExit("cropdeck split failed on the demo tray")
        pairs = [
            (cv2.imread(str(f)), cv2.imread(str(f).replace("_front", "_rear")))
            for f in sorted(out.glob("card_*_front.png"))
        ]
    if len(pairs) != 8:
        raise SystemExit(f"expected 8 pairs, got {len(pairs)}")
    return fronts, backs, pairs


def _pil(bgr: np.ndarray, height: int) -> Image.Image:
    img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return img.resize((round(img.width * height / img.height), height), Image.LANCZOS)


def compose(fronts, backs, pairs, theme: str) -> Image.Image:
    bg, panel, text, muted, arrow = THEMES[theme]
    font = ImageFont.truetype(io.BytesIO(inter(600)), 22)
    small = ImageFont.truetype(io.BytesIO(inter(400)), 17)
    pad, scan_h, card_h, gap = 30, 470, 210, 12
    scans = [_pil(fronts, scan_h), _pil(backs, scan_h)]
    cards = [(_pil(f, card_h), _pil(b, card_h)) for f, b in pairs]
    card_w = cards[0][0].width
    pair_w = 2 * card_w + 6
    left_w = 2 * scans[0].width + gap
    right_w = 4 * pair_w + 3 * 2 * gap
    arrow_w = 100
    W = pad + left_w + arrow_w + right_w + pad
    H = pad + 44 + scan_h + 34 + pad
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # left: the two scans as they come off the scanner
    d.text((pad, pad), "Your scans", font=font, fill=text)
    x = pad
    for scan, label in zip(scans, ("fronts", "backs, flipped in place"), strict=True):
        d.rounded_rectangle(
            [x - 1, pad + 43, x + scan.width, pad + 44 + scan_h], radius=6, outline=muted
        )
        img.paste(scan, (x, pad + 44))
        d.text((x, pad + 44 + scan_h + 8), label, font=small, fill=muted)
        x += scan.width + gap

    # arrow
    ax, ay = pad + left_w + 16, pad + 44 + scan_h // 2
    tip = ax + arrow_w - 32
    d.line([(ax, ay), (tip - 20, ay)], fill=arrow, width=10)
    d.polygon([(tip - 26, ay - 24), (tip, ay), (tip - 26, ay + 24)], fill=arrow)

    # right: every card upright and at true scale, front beside its own back
    rx = pad + left_w + arrow_w
    d.text((rx, pad), "cropdeck run: each front with its own back", font=font, fill=text)
    d.rounded_rectangle(
        [rx - 12, pad + 43, rx + right_w + 12, pad + 44 + scan_h], radius=10, fill=panel
    )
    top = pad + 44 + (scan_h - 2 * card_h - 3 * gap) // 2
    for k, (f, b) in enumerate(cards):
        cx = rx + (k % 4) * (pair_w + 2 * gap)
        cy = top + (k // 4) * (card_h + 2 * gap)
        img.paste(f, (cx, cy))
        img.paste(b, (cx + card_w + 6, cy))
        d.text((cx, cy + card_h + 2), f"{k + 1:04d}", font=small, fill=muted)
    return img


def main():
    fronts, backs, pairs = cut_tray()
    for theme in THEMES:
        path = ASSETS / f"demo-{theme}.png"
        compose(fronts, backs, pairs, theme).quantize(colors=256, dither=Image.Dither.NONE).save(
            path, optimize=True
        )
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
