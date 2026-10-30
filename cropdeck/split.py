"""
cropdeck split - cut flatbed scans full of trading cards into individual card images,
and with --pair, match every front with its own back.

    cropdeck split scans/ -o sorted/ --pair --expect 6
    cropdeck split scan.jpg --debug

Scan the full platen (A4), never "auto crop"; leave ~5-8 mm between cards and ~1 cm
from the platen edges. docs/scanning.md has the details.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from . import paths
from .card import guess_dpi
from .detect import backing_color, find_cards, refine_rect
from .extract import extract_card
from .guards import check_backs, thumbs
from .imageio import IMAGE_EXTS, imread_unicode, imwrite_unicode, save_params
from .output import pair_sheet, write_debug, write_manifest
from .pairing import match_by_position
from .state import load_state, save_state, scan_key


def detect(path: Path, out_dir: Path, args):
    """Read a scan and locate its cards. Returns (img, dpi, rects)."""
    img = imread_unicode(path)
    if img is None:
        print(f"  ! could not read {path.name}")
        return None, None, []

    dpi = guess_dpi(img, args.dpi)
    rects, mask, scale = find_cards(
        img, dpi, args.tolerance, args.debug, not args.no_split_merged, args.expect
    )

    if args.debug:
        write_debug(img, rects, scale, mask, out_dir / "_debug" / f"{path.stem}_debug.jpg")

    if not rects:
        print(
            f"  ! {path.name}: no cards found "
            f"(dpi guessed {dpi:g}; try --dpi, or --tolerance 0.25, and re-run --debug)"
        )
    elif args.expect and len(rects) != args.expect:
        print(
            f"  ! {path.name}: found {len(rects)}, expected {args.expect} "
            f"-- check the _debug overlay before trusting this one"
        )
    return img, dpi, rects


def render(img, rect, dpi, args, rotate):
    if not args.no_refine:
        rect = refine_rect(img, rect, dpi, args.tolerance)
    card = extract_card(
        img, rect, dpi, args.pad, args.out_dpi, not args.no_upright, backing_color(img)
    )
    if args.max_px and max(card.shape[:2]) > args.max_px:
        f = args.max_px / max(card.shape[:2])
        card = cv2.resize(card, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    if rotate:
        card = np.rot90(card, k=(-rotate // 90) % 4).copy()
    return card


def emit(card, out_dir: Path, name: str, args) -> Path:
    dst = out_dir / name
    imwrite_unicode(dst, card, save_params(args.format, args.quality))
    return dst


def run_single(files, out_dir: Path, args, rows: list, state: dict) -> int:
    n = 0
    todo = [f for f in files if scan_key(f) not in state["done"]]
    if len(todo) < len(files):
        print(f"  ({len(files) - len(todo)} scan(s) already done - skipping)")
    for path in todo:
        img, dpi, rects = detect(path, out_dir, args)
        for idx, rect in enumerate(rects, 1):
            n += 1
            card_no = state["next"]
            state["next"] += 1
            name = (
                f"{args.prefix}{card_no:04d}{args.format}"
                if args.flat
                else f"{path.stem}_card{idx:02d}{args.format}"
            )
            emit(render(img, rect, dpi, args, args.rotate), out_dir, name, args)
            rows.append(
                {
                    "card": f"{card_no:04d}",
                    "front": name,
                    "back": "",
                    "scan_front": path.name,
                    "scan_back": "",
                    "position": idx,
                }
            )
        if rects:
            state["done"][scan_key(path)] = len(rects)
            print(f"  + {path.name}: {len(rects)} card(s)")
    return n


def run_paired(files, out_dir: Path, args, rows: list, state: dict) -> int:
    """Fronts and backs alternate: scan 1 = fronts, scan 2 = the same tray's backs, ..."""
    if len(files) % 2:
        print(
            f"  ! odd number of scans ({len(files)}) - the last one has no partner "
            f"and will be skipped"
        )
    n = 0
    # an odd last scan has no partner; it was reported above and is left out here
    pairs = list(zip(files[0::2], files[1::2], strict=False))
    todo = [p for p in pairs if scan_key(p[0]) not in state["done"]]
    if len(todo) < len(pairs):
        print(f"  ({len(pairs) - len(todo)} tray(s) already done - skipping)")
    for f_path, b_path in todo:
        f_img, f_dpi, f_rects = detect(f_path, out_dir, args)
        b_img, b_dpi, b_rects = detect(b_path, out_dir, args)

        bg_f, bg_b = backing_color(f_img), backing_color(b_img)
        if len(f_rects) != len(b_rects):
            print(
                f"  ! MISMATCH {f_path.name} has {len(f_rects)} card(s) but "
                f"{b_path.name} has {len(b_rects)} -- pairing skipped for this tray, "
                f"fix the scan and re-run"
            )
            continue
        if not f_rects:
            continue

        f_th = thumbs(f_img, f_rects, f_dpi, args, bg_f)
        b_th = thumbs(b_img, b_rects, b_dpi, args, bg_b)
        problem = None if args.no_back_check else check_backs(f_th, b_th, state.get("back_ref"))
        if problem:
            print(
                f"  ! STOPPED on {f_path.name} / {b_path.name}: {problem}\n"
                f"    Nothing was written for this tray, and no later tray was "
                f"touched either.\n    Fix the scans and run again "
                f"(or --no-back-check to force it through)."
            )
            state["_stopped"] = True
            break
        if "back_ref" not in state and b_th:
            state["back_ref"] = np.median(np.stack(b_th), axis=0).tolist()

        order, why = match_by_position(
            f_rects, b_rects, args.back_order == "mirror", f_img.shape[1]
        )
        if order is None:
            print(
                f"  ! STOPPED on {f_path.name} / {b_path.name}: {why}\n"
                f"    Nothing was written for this tray."
            )
            state["_stopped"] = True
            break

        sheet = []
        for i, f_rect in enumerate(f_rects):
            n += 1
            card_no = state["next"]
            state["next"] += 1
            fn = f"{args.prefix}{card_no:04d}_front{args.format}"
            bn = f"{args.prefix}{card_no:04d}_back{args.format}"
            f_card = render(f_img, f_rect, f_dpi, args, args.rotate)
            b_card = render(
                b_img,
                b_rects[order[i]],
                b_dpi,
                args,
                args.rotate_back if args.rotate_back is not None else args.rotate,
            )
            emit(f_card, out_dir, fn, args)
            emit(b_card, out_dir, bn, args)
            sheet.append((f"{card_no:04d}", f_card, b_card))
            rows.append(
                {
                    "card": f"{card_no:04d}",
                    "front": fn,
                    "back": bn,
                    "scan_front": f_path.name,
                    "scan_back": b_path.name,
                    "position": i + 1,
                }
            )
        state["done"][scan_key(f_path)] = len(f_rects)
        state["done"][scan_key(b_path)] = len(f_rects)
        if not args.no_sheet and sheet:
            pair_sheet(sheet, out_dir / "_pairs" / f"{f_path.stem}_pairs.jpg")
        print(f"  + {f_path.name} / {b_path.name}: {len(f_rects)} card(s) paired")
    return n


def add_arguments(p: argparse.ArgumentParser):
    p.add_argument(
        "input",
        nargs="*",
        help=f"scan file(s) or folder(s)   [default: $CROPDECK_HOME/{paths.SCANS}]",
    )
    p.add_argument(
        "-o",
        "--out",
        default=None,
        help=f"output folder   [default: $CROPDECK_HOME/{paths.SORTED}]",
    )
    p.add_argument(
        "--dpi",
        type=float,
        default=None,
        help="scan resolution; auto-detected from A4 width if omitted",
    )
    p.add_argument(
        "--out-dpi",
        type=float,
        default=None,
        help="resample output to this dpi (default: keep scan dpi)",
    )
    p.add_argument(
        "--pad",
        type=float,
        default=1.0,
        metavar="MM",
        help="margin of backing kept around each card, in mm (default 1.0)",
    )
    p.add_argument(
        "--tolerance",
        type=float,
        default=0.18,
        help="how far from 63x88mm a shape may be and still count (default 0.18)",
    )
    p.add_argument(
        "--format",
        default=".png",
        choices=[".png", ".jpg", ".jpeg", ".webp", ".tif"],
        help="output format (default .png, lossless - best for listings)",
    )
    p.add_argument("--quality", type=int, default=95, help="JPEG/WebP quality (default 95)")
    p.add_argument(
        "--max-px",
        type=int,
        default=None,
        help="cap the long edge in pixels (e.g. 2000 for marketplace uploads)",
    )
    p.add_argument(
        "--rotate",
        type=int,
        default=0,
        choices=[0, 90, 180, 270],
        help="rotate every output by this many degrees clockwise",
    )
    p.add_argument(
        "--rotate-back",
        type=int,
        default=None,
        choices=[0, 90, 180, 270],
        help="separate rotation for back images (default: same as --rotate)",
    )
    p.add_argument("--prefix", default="card_", help="filename prefix for numbered outputs")
    p.add_argument(
        "--flat", action="store_true", help="name outputs card_0001... instead of <scan>_cardNN"
    )
    p.add_argument(
        "--expect",
        type=int,
        default=None,
        help="cards per scan; warns loudly when a scan doesn't match",
    )
    p.add_argument(
        "--pair",
        action="store_true",
        help="fronts and backs alternate (scan 1 = fronts, scan 2 = those same "
        "cards' backs, scan 3 = next tray's fronts, ...). Outputs "
        "card_0001_front / card_0001_back.",
    )
    p.add_argument(
        "--back-order",
        default="same",
        choices=["same", "mirror"],
        help="'same' (default) = you flipped each card in its own slot; "
        "'mirror' = you flipped the whole tray left-to-right as a block",
    )
    p.add_argument(
        "--no-split-merged", action="store_true", help="don't try to cut touching cards apart"
    )
    p.add_argument(
        "--status", action="store_true", help="just say how far along you are, process nothing"
    )
    p.add_argument(
        "--no-sheet", action="store_true", help="don't write the per-tray front/back proof sheet"
    )
    p.add_argument(
        "--no-back-check",
        action="store_true",
        help="skip the 'is the second scan really the backs?' safety check",
    )
    p.add_argument(
        "--restart",
        action="store_true",
        help="forget what was already done and re-cut every scan from 0001",
    )
    p.add_argument(
        "--no-refine",
        action="store_true",
        help="skip the full-resolution re-measure of each card (faster, "
        "slightly less well centred)",
    )
    p.add_argument(
        "--no-upright",
        action="store_true",
        help="keep cards in the orientation they were laid on the glass "
        "instead of standing them up as portrait",
    )
    p.add_argument(
        "--debug", action="store_true", help="write overlay images showing what was detected"
    )


def run(args) -> int:
    files: list[Path] = []
    roots: list[Path] = []
    for item in args.input or [paths.home() / paths.SCANS]:
        pth = Path(item).expanduser()
        if pth.is_dir():
            roots.append(pth)
            files += sorted(
                f for f in pth.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS
            )
        elif pth.is_file():
            roots.append(pth.parent)
            files.append(pth)
        else:
            print(f"! not found: {item}", file=sys.stderr)

    if not files:
        print("Nothing to do - no images found.", file=sys.stderr)
        return 1

    if args.out:
        out_dir = Path(args.out).expanduser()
    elif not args.input:
        out_dir = paths.home() / paths.SORTED
    else:
        out_dir = roots[0] / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    # never re-ingest our own output
    files = [f for f in files if out_dir not in f.parents]

    print(f"Scanning {len(files)} file(s) -> {out_dir}")
    state = {"next": 1, "done": {}} if args.restart else load_state(out_dir)
    if args.status:
        done = sorted(state["done"])
        print(f"{state['next'] - 1} card(s) cut so far; next number is {state['next']:04d}.")
        print(f"{len(done)} scan(s) already processed:")
        for k in done:
            print(f"  - {k.split('|')[0]}")
        todo = [f.name for f in files if scan_key(f) not in state["done"]]
        print(f"{len(todo)} scan(s) waiting:" if todo else "Nothing new waiting.")
        for t in todo:
            print(f"  - {t}")
        return 0
    rows: list = []
    n = (
        run_paired(files, out_dir, args, rows, state)
        if args.pair
        else run_single(files, out_dir, args, rows, state)
    )
    stopped = state.pop("_stopped", False)
    save_state(out_dir, state)

    if rows:
        man = write_manifest(rows, out_dir, append=not args.restart)
        print(
            f"\nDone: {n} card{'s (front+back)' if args.pair else ' image(s)'} "
            f"-> {out_dir}\nManifest: {man}"
        )
    elif stopped:
        print("\nStopped before writing anything - see the message above.")
    else:
        print(
            "\nDone: nothing new - every scan in that folder has already been cut."
            "\n(Add new scans and run again, or pass --restart to redo the lot.)"
        )
    if args.debug:
        print(f"Debug overlays in {out_dir / '_debug'}")

    if rows and not args.no_sheet and args.pair:
        print(f"  Check the pairings at a glance: {out_dir / '_pairs'}")
    total = state["next"] - 1
    trays = len([k for k in state["done"]]) // (2 if args.pair else 1)
    print("\n--- where you are ------------------------------------------")
    print(f"  {total} card(s) cut so far, from {trays} tray(s).")
    print(f"  Next card will be number {state['next']:04d}.")
    print("  Finished scans can stay in the scans folder - they are skipped.")
    print("------------------------------------------------------------")
    return 0
