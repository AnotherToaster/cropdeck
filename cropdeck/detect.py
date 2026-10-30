"""
Finding the cards on a platen scan: separate card from backing, pull out card-shaped
rectangles, put them in reading order, then re-measure each one at full resolution.
"""

from __future__ import annotations

import cv2
import numpy as np

from .card import CARD_ASPECT, CARD_H_MM, CARD_W_MM


def background_distance(bgr):
    """
    How far every pixel sits from the backing colour, in CIE-Lab.

    Thresholding brightness cannot separate a dark blue card back from a black sheet -
    both are dark. Distance from the *measured* backing colour can, and it also makes
    the light-lid case work with no switch to flip: the backing is whatever colour the
    edge of the platen is, and a card is anything that doesn't look like it.
    """
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    b = max(4, min(h, w) // 60)
    border = np.concatenate(
        [
            lab[:b].reshape(-1, 3),
            lab[-b:].reshape(-1, 3),
            lab[:, :b].reshape(-1, 3),
            lab[:, -b:].reshape(-1, 3),
        ]
    )
    bg = np.median(border, axis=0)  # median survives a card overhanging the edge
    return np.linalg.norm(lab - bg, axis=2)


def fill_holes(mask):
    """Fill interior holes (dark card art read as background) WITHOUT growing the outline."""
    filled = np.zeros_like(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


def subdivide(rect, card_w, card_h, tolerance):
    """
    Cards laid touching each other survive as one blob. If a blob measures a whole
    number of cards across and down, cut it back into that grid instead of binning it.
    Returns a list of rects (one element = the rect itself if it is a single card).
    """
    (cx, cy), (rw, rh), angle = rect
    best = None
    for cw, chh in ((card_w, card_h), (card_h, card_w)):  # card upright or sideways
        nx, ny = round(rw / cw), round(rh / chh)
        if nx < 1 or ny < 1 or nx * ny > 24:
            continue
        if abs(rw - nx * cw) > cw * tolerance or abs(rh - ny * chh) > chh * tolerance:
            continue
        if best is None or nx * ny > best[0] * best[1]:
            best = (nx, ny, cw, chh)
    if best is None:
        return []
    nx, ny, cw, chh = best
    if nx == 1 and ny == 1:
        return [rect]

    # step across the blob in its own rotated frame
    th = np.deg2rad(angle)
    ux, uy = np.cos(th), np.sin(th)  # unit vector along the blob's width
    vx, vy = -np.sin(th), np.cos(th)  # unit vector along its height
    step_x, step_y = rw / nx, rh / ny
    out = []
    for j in range(ny):
        for i in range(nx):
            ox = (i + 0.5) * step_x - rw / 2
            oy = (j + 0.5) * step_y - rh / 2
            out.append(
                (((cx + ox * ux + oy * vx), (cy + ox * uy + oy * vy)), (step_x, step_y), angle)
            )
    return out


def rects_from_mask(mask, card_w, card_h, tolerance, split_merged=True):
    """Pull card-shaped rotated rects out of a binary mask."""
    want_area = card_w * card_h
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        rect = cv2.minAreaRect(c)
        (rw, rh) = rect[1]
        if rw < 1 or rh < 1:
            continue
        area = rw * rh
        # a card is a solid rectangle - the contour must actually fill its own box
        if cv2.contourArea(c) < 0.85 * area:
            continue

        w_, h_ = (rw, rh) if rw <= rh else (rh, rw)  # normalise to portrait
        single = (
            want_area * (1 - tolerance) ** 2 <= w_ * h_ <= want_area * (1 + tolerance) ** 2
            and abs(w_ / h_ - CARD_ASPECT) <= CARD_ASPECT * tolerance
        )
        if single:
            out.append(rect)
        elif split_merged and area > want_area * 1.5:
            out.extend(subdivide(rect, card_w, card_h, tolerance))
    return out


def bbox_height(rect):
    """Vertical extent of a rotated rect on the platen, whichever way the card lies."""
    (_, _), (rw, rh), a = rect
    t = np.deg2rad(a)
    return abs(rw * np.sin(t)) + abs(rh * np.cos(t))


def reading_order(rects):
    """
    Top-to-bottom by row, left-to-right within a row.

    Rows are found by looking for the gaps between them, NOT by bucketing y into
    fixed bands. Bucketing put two cards of the same physical row on opposite sides
    of a band boundary whenever that row happened to straddle one - which silently
    reordered one scan and not the other, and mispaired every card from there on.
    """
    if not rects:
        return []
    rs = sorted(rects, key=lambda r: r[0][1])
    limit = float(np.median([bbox_height(r) for r in rs])) * 0.6
    rows, cur = [], [rs[0]]
    for r in rs[1:]:
        if r[0][1] - cur[0][0][1] > limit:  # far enough below the row's top card
            rows.append(cur)
            cur = [r]
        else:
            cur.append(r)
    rows.append(cur)
    out = []
    for row in rows:
        out += sorted(row, key=lambda r: r[0][0])
    return out


def find_cards(
    img,
    dpi: float,
    tolerance: float,
    debug: bool = False,
    split_merged: bool = True,
    expect: int | None = None,
):
    """Return a list of cv2 rotated rects, one per detected card, in reading order."""
    # Work on a downscaled copy: faster, and it suppresses foil speckle.
    scale = 1.0
    max_side = 1600
    if max(img.shape[:2]) > max_side:
        scale = max_side / max(img.shape[:2])
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = img.copy()

    dist = background_distance(small)

    px_per_mm = dpi / 25.4 * scale
    card_w, card_h = CARD_W_MM * px_per_mm, CARD_H_MM * px_per_mm

    # Two sweeps, keeping whichever combination finds the most cards.
    #  * how different from the backing a pixel must be to count as card
    #  * how hard to prise apart cards that were laid touching. Morphological OPENING
    #    removes a thin bridge without shrinking the cards (erode then dilate restores
    #    the shape). No CLOSE anywhere - closing is what fuses neighbours together.
    best, best_mask = [], None
    for t in (12, 16, 20, 26, 34, 45, 60, 80):
        base = fill_holes((dist > t).astype(np.uint8) * 255)
        for mm in (0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
            if mm == 0.0:
                m = base
            else:
                k = max(3, int(round(mm / 25.4 * dpi * scale)) | 1)
                if k > min(small.shape[:2]) // 4:
                    break
                m = cv2.morphologyEx(
                    base, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
                )
            found = rects_from_mask(m, card_w, card_h, tolerance, split_merged)
            if len(found) > len(best):
                best, best_mask = found, m
        if expect and len(best) == expect:
            break

    # scale rects back up to full-resolution coordinates
    rects = [
        ((cx / scale, cy / scale), (rw / scale, rh / scale), a) for (cx, cy), (rw, rh), a in best
    ]

    return reading_order(rects), (best_mask if debug else None), scale


def refine_rect(img, rect, dpi: float, tolerance: float):
    """
    Re-measure one card at full resolution.

    The first pass runs on a downscaled image with one threshold chosen for the whole
    platen, so a card whose edge happens to sit close to the backing colour can come
    out a few millimetres off-centre. Here we look at just this card, in a window that
    is almost entirely card plus backing, where the split is unambiguous - and the
    centre we get is good to a pixel or two. Falls back to the original rect if the
    refined one doesn't measure like a card.
    """
    (cx, cy), (rw, rh), angle = rect
    margin = 6.0 / 25.4 * dpi
    half = max(rw, rh) / 2 + margin
    x0, y0 = int(max(0, cx - half)), int(max(0, cy - half))
    x1, y1 = int(min(img.shape[1], cx + half)), int(min(img.shape[0], cy + half))
    win = img[y0:y1, x0:x1]
    if win.size == 0 or min(win.shape[:2]) < 10:
        return rect

    dist = background_distance(win)
    ppm = dpi / 25.4
    card_w, card_h = CARD_W_MM * ppm, CARD_H_MM * ppm

    best, best_err = rect, None
    for t in (16, 22, 30, 40, 55, 70, 90, 110):
        cs, _ = cv2.findContours(
            fill_holes((dist > t).astype(np.uint8) * 255),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if not cs:
            continue
        c = max(cs, key=cv2.contourArea)
        (nx, ny), (nw, nh), na = cv2.minAreaRect(c)
        if nw < 1 or nh < 1:
            continue
        w_, h_ = (nw, nh) if nw <= nh else (nh, nw)
        # must still look like a card, and fill its own bounding box like one
        gate = min(tolerance, 0.10)
        if abs(w_ - card_w) > card_w * gate or abs(h_ - card_h) > card_h * gate:
            continue
        if cv2.contourArea(c) < 0.93 * nw * nh:
            continue
        # worst axis, not area - too wide plus too short would cancel out in area
        err = max(abs(w_ - card_w) / card_w, abs(h_ - card_h) / card_h)
        if best_err is None or err < best_err:
            best_err = err
            best = ((nx + x0, ny + y0), (nw, nh), na)
    return best


def backing_color(bgr):
    """Median colour of the platen edge - i.e. the sheet the cards are lying on."""
    h, w = bgr.shape[:2]
    b = max(4, min(h, w) // 60)
    border = np.concatenate(
        [
            bgr[:b].reshape(-1, 3),
            bgr[-b:].reshape(-1, 3),
            bgr[:, :b].reshape(-1, 3),
            bgr[:, -b:].reshape(-1, 3),
        ]
    )
    return np.median(border, axis=0)
