"""
Reading one scan and cutting its cards out: shared by single-scan splitting and the paired
tray-by-tray run (process.py). Nothing here prints; problems come back as notes for the caller.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .card import guess_dpi
from .detect import backing_color, find_cards, refine_rect
from .extract import extract_card
from .imageio import imread_unicode, imwrite_unicode, save_params
from .output import write_debug


def detect(path: Path, out_dir: Path, opts):
    """Read a scan and locate its cards. Returns (img, dpi, rects, notes); img is None when the
    file cannot be read."""
    img = imread_unicode(path)
    if img is None:
        return None, None, [], [f"could not read {path.name}"]

    dpi = guess_dpi(img, opts.dpi)
    rects, mask, scale = find_cards(
        img, dpi, opts.tolerance, opts.debug, not opts.no_split_merged, opts.expect
    )
    if opts.debug:
        write_debug(img, rects, scale, mask, out_dir / "_debug" / f"{path.stem}_debug.jpg")

    notes = []
    if not rects:
        notes.append(
            f"{path.name}: no cards found "
            f"(dpi guessed {dpi:g}; try --dpi, or --tolerance 0.25, and re-run --debug)"
        )
    elif opts.expect and len(rects) != opts.expect:
        notes.append(
            f"{path.name}: found {len(rects)}, expected {opts.expect} "
            f"-- check the _debug overlay before trusting this one"
        )
    return img, dpi, rects, notes


def render(img, rect, dpi, opts, rotate):
    """One card cut out of img at true scale, stood upright and rotated as asked."""
    if not opts.no_refine:
        rect = refine_rect(img, rect, dpi, opts.tolerance)
    card = extract_card(
        img, rect, dpi, opts.pad, opts.out_dpi, not opts.no_upright, backing_color(img)
    )
    if opts.max_px and max(card.shape[:2]) > opts.max_px:
        f = opts.max_px / max(card.shape[:2])
        card = cv2.resize(card, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    if rotate:
        card = np.rot90(card, k=(-rotate // 90) % 4).copy()
    return card


def write(card, out_dir: Path, name: str, opts) -> Path:
    dst = out_dir / name
    imwrite_unicode(dst, card, save_params(opts.format, opts.quality))
    return dst
