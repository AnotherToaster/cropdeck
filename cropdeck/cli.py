"""
The `cropdeck` command: one entry point for every step.

    cropdeck run [FOLDER]       crop + pair FOLDER/scans into FOLDER/sorted
                                (--names and --tracker add the optional steps)
    cropdeck status [FOLDER]    how far along FOLDER is, without processing anything
    cropdeck split ...          crop (+ pair) with every option
    cropdeck name SORTED        read names off the cropped fronts (OCR)
    cropdeck track [SORTED]     build / update the tracker workbook

FOLDER defaults to $CROPDECK_HOME, or the current directory.

Each step lives in its own module with add_arguments() and run(). The modules are
imported only when their subcommand runs, so cropping works without Tesseract or
openpyxl installed.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from . import __version__, paths

STEPS = {
    "split": ("split", "crop the cards out of flatbed scans; --pair matches fronts with backs"),
    "name": ("name", "read each card's name and number (OCR) and rename front and back together"),
    "track": ("track", "build or update the tracker workbook from cards.csv"),
    "ui": ("ui.server", "open the browser interface (early: in development)"),
}


def _step(name: str):
    return importlib.import_module(f".{STEPS[name][0]}", __package__)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cropdeck",
        description="Flatbed scans of trading cards -> cropped, paired front/back images.",
    )
    p.add_argument("--version", action="version", version=f"cropdeck {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    r = sub.add_parser(
        "run",
        help="crop and pair everything new in FOLDER/scans",
        description="Crop and pair FOLDER/scans into FOLDER/sorted. Odd scans "
        "are fronts, even scans the same tray's backs.",
    )
    r.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="folder holding scans/ [default: $CROPDECK_HOME or the current directory]",
    )
    r.add_argument(
        "--expect",
        type=int,
        default=8,
        help="cards per scan (default 8: two across, four down, lying sideways)",
    )
    r.add_argument("--dpi", type=float, default=None, help="scan resolution if not A4-detectable")
    r.add_argument("--names", action="store_true", help="also read names and numbers (OCR)")
    r.add_argument("--tracker", action="store_true", help="also update the tracker workbook")
    r.add_argument("--debug", action="store_true", help="write detection overlays to sorted/_debug")

    s = sub.add_parser("status", help="how far along FOLDER is; processes nothing")
    s.add_argument("folder", nargs="?", default=None)

    # Listed here for the overview only; main() hands a step's arguments straight to the
    # step's own parser, which is where its options and --help live.
    for name, (_, text) in STEPS.items():
        sub.add_parser(name, help=text)
    return p


def _folders(folder: str | None) -> tuple[Path, Path]:
    base = Path(folder).expanduser() if folder else paths.home()
    return base / paths.SCANS, base / paths.SORTED


def _run_step(name: str, argv: list[str]) -> int:
    """Run one step with an argv of its own, exactly as `cropdeck <name> ...` would."""
    p = argparse.ArgumentParser(prog=f"cropdeck {name}", description=STEPS[name][1])
    mod = _step(name)
    mod.add_arguments(p)
    return mod.run(p.parse_args(argv))


def run(args) -> int:
    scans, sorted_dir = _folders(args.folder)
    argv = [str(scans), "-o", str(sorted_dir), "--pair", "--expect", str(args.expect)]
    if args.dpi:
        argv += ["--dpi", str(args.dpi)]
    if args.debug:
        argv.append("--debug")
    print("=== crop and pair ===")
    rc = _run_step("split", argv)
    if rc:
        return rc
    if args.names:
        print("\n=== names ===")
        rc = _run_step("name", [str(sorted_dir)])
        if rc:
            return rc
    if args.tracker:
        print("\n=== tracker ===")
        rc = _run_step("track", [str(sorted_dir), "-o", str(sorted_dir.parent / paths.TRACKER)])
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] and argv[0] in STEPS:
        return _run_step(argv[0], argv[1:])
    args = _parser().parse_args(argv)
    if args.command == "run":
        return run(args)
    scans, sorted_dir = _folders(args.folder)
    return _run_step("split", [str(scans), "-o", str(sorted_dir), "--pair", "--status"])
