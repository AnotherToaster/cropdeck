"""
What a run leaves behind besides the cards: detection overlays, the per-tray proof
sheet, and the new rows for the cards.csv manifest.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import manifest
from .imageio import imwrite_unicode, save_params


def write_debug(img, rects, scale, mask, path: Path):
    vis = img.copy()
    for i, rect in enumerate(rects, 1):
        box = cv2.boxPoints(rect).astype(int)
        cv2.drawContours(vis, [box], 0, (0, 0, 255), max(2, img.shape[1] // 400))
        cv2.putText(
            vis,
            str(i),
            tuple(box[0]),
            cv2.FONT_HERSHEY_SIMPLEX,
            img.shape[1] / 700,
            (0, 0, 255),
            max(2, img.shape[1] // 500),
        )
    h = 1400
    vis = cv2.resize(vis, (int(vis.shape[1] * h / vis.shape[0]), h))
    imwrite_unicode(path, vis, save_params(path.suffix, 90))
    if mask is not None:
        imwrite_unicode(path.with_name(path.stem + "_mask.jpg"), mask, save_params(".jpg", 85))


def pair_sheet(items, path: Path):
    """
    One JPEG per tray: every front next to the back that was matched to it.

    Card backs look alike, so a mispairing is invisible in the output folder. This
    puts the whole tray on one page so you can check it in a couple of seconds -
    a scuff or a bent corner on a back is enough to confirm it sits with its front.
    """
    h, gap = 260, 8
    cells = []
    for label, front, back in items:

        def fit(im):
            return cv2.resize(im, (int(im.shape[1] * h / im.shape[0]), h))

        cell = np.hstack([fit(front), np.full((h, gap, 3), 255, np.uint8), fit(back)])
        cell = cv2.copyMakeBorder(cell, 26, 10, 10, 24, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(cell, label, (12, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cells.append(cell)

    per_row = 3
    rows = [np.hstack(cells[i : i + per_row]) for i in range(0, len(cells), per_row)]
    w = max(r.shape[1] for r in rows)
    rows = [
        np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 255, np.uint8)])
        if r.shape[1] < w
        else r
        for r in rows
    ]
    imwrite_unicode(path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


def write_manifest(rows, out_dir: Path, append: bool = False):
    """
    Add this run's rows to cards.csv. When appending, previous rows are read back first,
    with any columns the name step added or that you typed in yourself.
    """
    return manifest.write(out_dir, (manifest.read(out_dir) if append else []) + rows)
