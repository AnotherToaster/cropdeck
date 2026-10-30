"""
Reading and writing images. cv2.imread/imwrite fail on non-ASCII paths on Windows, so
every image goes through numpy's file IO and cv2's in-memory codecs instead.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def imread_unicode(path: Path):
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, img, params=None) -> bool:
    ok, buf = cv2.imencode(path.suffix, img, params or [])
    if not ok:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))
    return True


def save_params(fmt: str, quality: int):
    if fmt in (".jpg", ".jpeg"):
        return [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1]
    if fmt == ".png":
        return [cv2.IMWRITE_PNG_COMPRESSION, 6]
    if fmt in (".webp",):
        return [cv2.IMWRITE_WEBP_QUALITY, quality]
    return []
