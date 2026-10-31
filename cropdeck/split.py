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

from . import cut, manifest, paths, process, trays
from .output import write_manifest
from .state import load_state, save_state, scan_key


def detect(path: Path, out_dir: Path, args):
    """cut.detect, with its notes printed."""
    img, dpi, rects, notes = cut.detect(path, out_dir, args)
    for note in notes:
        print(f"  ! {note}")
    return img, dpi, rects


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
            cut.write(cut.render(img, rect, dpi, args, args.rotate), out_dir, name, args)
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


BACKS_KINDS = (process.NOTBACKS, process.SWAPPED)


def run_paired(files, out_dir: Path, args, state: dict, append: bool) -> tuple[int, bool]:
    """Fronts and backs alternate: scan 1 = fronts, scan 2 = the same tray's backs, ...
    Prints process.run's events; returns (cards written, whether a tray was refused)."""
    folder = trays.build(files, state, manifest.read(out_dir))
    done = [t for t in folder if t.status == trays.DONE]
    if done:
        print(f"  ({len(done)} tray(s) already done - skipping)")
    for t in folder:
        if t.status == trays.SKIPPED:
            print(f"  - tray {t.n} ({t.front.name}) is skipped")
    n, stopped = 0, False
    for event in process.run(trays.runnable(folder), args, state, out_dir, append):
        if isinstance(event, process.Note):
            print(f"  ! {event.text}")
        elif isinstance(event, process.TrayDone):
            t = event.tray
            n += event.last - event.first + 1
            print(
                f"  + {t.front.name} / {t.back.name}: {event.last - event.first + 1} card(s) paired"
            )
        elif isinstance(event, process.TrayStopped):
            stopped = True
            t = event.tray
            hint = " (or --no-back-check to force it through)" if event.kind in BACKS_KINDS else ""
            print(
                f"  ! STOPPED on {t.front.name} / {t.back.name}: {event.message}\n"
                f"    Nothing was written for this tray, and no later tray was touched either.\n"
                f"    Fix the scans and run again{hint}, or choose a fix in `cropdeck ui`."
            )
    if not stopped:
        waiting = trays.next_up(folder)
        if waiting and waiting.status == trays.NEEDS_BACKS:
            print(f"  ! tray {waiting.n} ({waiting.front.name}) waits for its backs scan")
        elif waiting and waiting.status == trays.STOPPED:
            stopped = True
            print(
                f"  ! tray {waiting.n} ({waiting.front.name}) stopped earlier: "
                f"{waiting.stop['message']}\n    Fix the scans, or choose a fix in `cropdeck ui`."
            )
    return n, stopped


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
        "card_0001_front / card_0001_rear.",
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


def options(**overrides) -> argparse.Namespace:
    """split's options at their defaults, with overrides - for callers that are not the command
    line (the browser interface, the tests)."""
    p = argparse.ArgumentParser()
    add_arguments(p)
    opts = p.parse_args([])
    for k, v in overrides.items():
        if not hasattr(opts, k):
            raise TypeError(f"unknown split option {k!r}")
        setattr(opts, k, v)
    return opts


def run(args) -> int:
    files: list[Path] = []
    roots: list[Path] = []
    for item in args.input or [paths.home() / paths.SCANS]:
        pth = Path(item).expanduser()
        if pth.is_dir():
            roots.append(pth)
            files += trays.scans_in(pth)
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
    if args.pair:
        n, stopped = run_paired(files, out_dir, args, state, append=not args.restart)
        man = out_dir / manifest.FILE
    else:
        rows: list = []
        n, stopped = run_single(files, out_dir, args, rows, state), False
        save_state(out_dir, state)
        man = write_manifest(rows, out_dir, append=not args.restart) if rows else None

    if n:
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

    if n and not args.no_sheet and args.pair:
        print(f"  Check the pairings at a glance: {out_dir / '_pairs'}")
    total = state["next"] - 1
    tray_count = len(state["done"]) // (2 if args.pair else 1)
    print("\n--- where you are ------------------------------------------")
    print(f"  {total} card(s) cut so far, from {tray_count} tray(s).")
    print(f"  Next card will be number {state['next']:04d}.")
    print("  Finished scans can stay in the scans folder - they are never cut twice.")
    print("------------------------------------------------------------")
    # a tray that was refused is a problem the caller must not miss
    return 1 if stopped else 0
