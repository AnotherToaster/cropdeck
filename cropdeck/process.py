"""
Processing trays, one at a time, as a stream of events - the core shared by
`cropdeck split --pair` (which prints them) and the browser interface (which shows them live).

A tray is refused whole: when its fronts and backs do not add up, nothing of it is written and
the run stops there, so every later tray waits and card numbers stay in tray order. Each card is
written the moment it is cut and paired; the manifest and the state file are saved after every
tray, so stopping or crashing loses nothing that was done.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import cut, guards
from .card import FRONT, REAR
from .detect import backing_color
from .output import pair_sheet, write_manifest
from .pairing import match_by_position, match_slots, moved_slots
from .state import save_state, scan_key
from .trays import Tray, choices

COUNT, NOTBACKS, SWAPPED, MOVED, UNREADABLE = "count", "notbacks", "swapped", "moved", "unreadable"


@dataclass
class Note:
    text: str  # something worth a look that does not stop the tray


@dataclass
class TrayStart:
    tray: Tray


@dataclass
class CardDone:
    tray: Tray
    card: int  # card number
    index: int  # 1-based position in the tray
    count: int  # cards in the tray
    front: str  # file names in the output folder
    rear: str


@dataclass
class TrayDone:
    tray: Tray
    first: int
    last: int


@dataclass
class TrayStopped:
    tray: Tray
    kind: str  # COUNT, NOTBACKS, SWAPPED, MOVED or UNREADABLE
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class RunDone:
    cards: int
    trays: int
    halted: bool = False  # stopped on request after a tray


def _rects(rects) -> list:
    """Detected cards in a form the state file can hold: [[cx, cy], [w, h], angle]."""
    return [[[float(c) for c in r[0]], [float(c) for c in r[1]], float(r[2])] for r in rects]


def _stop(tray: Tray, state: dict, out_dir: Path, kind: str, message: str, detail: dict):
    choices(state, tray.n)["stop"] = {
        "kind": kind,
        "message": message,
        "keys": tray.keys,
        "detail": detail,
    }
    save_state(out_dir, state)
    tray.status, tray.stop = "stopped", choices(state, tray.n)["stop"]
    return TrayStopped(tray, kind, message, detail)


def process_tray(tray: Tray, opts, state: dict, out_dir: Path, append: bool) -> Iterator:
    """Cut and pair one tray. Yields TrayStart, Notes, then CardDone per card and TrayDone, or a
    TrayStopped with nothing written."""
    chosen = choices(state, tray.n)
    f_path, b_path = (tray.back, tray.front) if chosen.get("swap") else (tray.front, tray.back)
    yield TrayStart(tray)

    f_img, f_dpi, f_rects, notes = cut.detect(f_path, out_dir, opts)
    b_img, b_dpi, b_rects, b_notes = cut.detect(b_path, out_dir, opts)
    for text in notes + b_notes:
        yield Note(text)
    if f_img is None or b_img is None:
        yield _stop(tray, state, out_dir, UNREADABLE, (notes + b_notes)[0], {})
        return

    mirror = opts.back_order == "mirror"
    width = f_img.shape[1]
    detail = {
        "fronts": _rects(f_rects),
        "backs": _rects(b_rects),
        "size": [int(f_img.shape[1]), int(f_img.shape[0])],
        "back_size": [int(b_img.shape[1]), int(b_img.shape[0])],
        "mirror": mirror,
    }
    if not f_rects or len(f_rects) != len(b_rects):
        slots = match_slots(f_rects, b_rects, mirror, width) if f_rects else []
        detail["missing"] = [i + 1 for i, j in enumerate(slots) if j is None]
        if not (chosen.get("pairs_only") and any(j is not None for j in slots)):
            yield _stop(
                tray,
                state,
                out_dir,
                COUNT,
                f"{f_path.name} has {len(f_rects)} card(s) but {b_path.name} has {len(b_rects)}",
                {**detail, "front_count": len(f_rects), "back_count": len(b_rects)},
            )
            return
        order = slots
    else:
        order = None

    bg_f, bg_b = backing_color(f_img), backing_color(b_img)
    f_th = guards.thumbs(f_img, f_rects, f_dpi, opts, bg_f)
    b_th = guards.thumbs(b_img, b_rects, b_dpi, opts, bg_b)
    refs = guards.back_refs(state)
    trust = opts.no_back_check or chosen.get("keep") or chosen.get("new_back")
    problem = None if trust else guards.check_backs(f_th, b_th, refs)
    if problem:
        yield _stop(tray, state, out_dir, problem[0], problem[1], detail)
        return

    if order is None:
        order, why = match_by_position(f_rects, b_rects, mirror, width)
        if order is None:
            detail["moved"] = [i + 1 for i in moved_slots(f_rects, b_rects, mirror, width)]
            yield _stop(tray, state, out_dir, MOVED, why, detail)
            return
    if chosen.get("new_back") or not refs:
        guards.learn_back(state, b_th)

    pairs = [(i, j) for i, j in enumerate(order) if j is not None]
    rot_b = opts.rotate_back if opts.rotate_back is not None else opts.rotate
    rows, sheet, first = [], [], state["next"]
    for k, (i, j) in enumerate(pairs, 1):
        no = state["next"]
        state["next"] += 1
        fn = f"{opts.prefix}{no:04d}_{FRONT}{opts.format}"
        bn = f"{opts.prefix}{no:04d}_{REAR}{opts.format}"
        f_card = cut.render(f_img, f_rects[i], f_dpi, opts, opts.rotate)
        b_card = cut.render(b_img, b_rects[j], b_dpi, opts, rot_b)
        cut.write(f_card, out_dir, fn, opts)
        cut.write(b_card, out_dir, bn, opts)
        sheet.append((f"{no:04d}", f_card, b_card))
        rows.append(
            {
                "card": f"{no:04d}",
                "front": fn,
                "back": bn,
                "scan_front": f_path.name,
                "scan_back": b_path.name,
                "position": i + 1,
            }
        )
        yield CardDone(tray, no, k, len(pairs), fn, bn)

    write_manifest(rows, out_dir, append=append)
    state["done"][scan_key(f_path)] = len(pairs)
    state["done"][scan_key(b_path)] = len(pairs)
    chosen.pop("stop", None)
    if chosen.get("await_after") is not None:  # the rescan arrived and is used: pin it
        chosen["back"] = tray.back.name
        chosen.pop("await_after")
    save_state(out_dir, state)
    if not opts.no_sheet and sheet:
        pair_sheet(sheet, out_dir / "_pairs" / f"{f_path.stem}_pairs.jpg")
    tray.status, tray.cards = "done", (first, state["next"] - 1)
    yield TrayDone(tray, first, state["next"] - 1)


def run(
    todo: list[Tray],
    opts,
    state: dict,
    out_dir: Path,
    append: bool = True,
    halt: Callable[[], bool] = lambda: False,
) -> Iterator:
    """Process the given trays in order (trays.runnable gives them) and end with RunDone. Stops
    at the first tray that is refused; halt() is asked after each tray ("stop after this tray")."""
    cards = trays = 0
    for k, tray in enumerate(todo):
        stopped = False
        for event in process_tray(tray, opts, state, out_dir, append):
            if isinstance(event, TrayDone):
                cards += event.last - event.first + 1
                trays += 1
                append = True
            stopped = stopped or isinstance(event, TrayStopped)
            yield event
        if stopped:
            break
        if k + 1 < len(todo) and halt():
            yield RunDone(cards, trays, halted=True)
            return
    yield RunDone(cards, trays)
