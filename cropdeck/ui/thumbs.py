"""
Small images for the pages: card thumbnails and downscaled scans. A grid never gets a full-size
card. Both are made on first request and kept in sorted/_thumbs/ (cropdeck's own output folder;
the scans folder is only read), and made again when their source changes.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import cv2

from ..imageio import imread_unicode, imwrite_unicode, save_params

CACHE = "_thumbs"
CARD_HEIGHT = 176  # px: 2x the 88 px a card is drawn at, sharp on high-density screens
SCAN_EDGE = 900  # px: the long edge of a scan shown on the guard-stop page


def thumb_url(name: str) -> str:
    return f"/thumb/{quote(name)}"


def _make(src: Path, dst: Path, fit) -> Path | None:
    """dst, made from src if it is missing or older. None if src cannot be read."""
    try:
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
    except OSError:
        return None
    img = imread_unicode(src)
    if img is None:
        return None
    h, w = img.shape[:2]
    f = fit(w, h)
    small = cv2.resize(
        img, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    imwrite_unicode(dst, small, save_params(".jpg", 82))
    return dst


def card(src: Path, sorted_dir: Path) -> Path | None:
    return _make(
        src, sorted_dir / CACHE / f"{src.stem}.jpg", lambda w, h: min(1.0, CARD_HEIGHT / h)
    )


def scan(src: Path, sorted_dir: Path) -> Path | None:
    return _make(
        src,
        sorted_dir / CACHE / "scans" / f"{src.stem}.jpg",
        lambda w, h: min(1.0, SCAN_EDGE / max(w, h)),
    )
