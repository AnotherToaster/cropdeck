"""
cropdeck name - read the Pokemon name off each cropped card and rename the files.

Runs AFTER cropdeck split --pair, over its output folder. Renames each front and its matching
back together, so the pairing survives:

    card_0001_front.png  ->  0001_Charmander_9-25_front.png
    card_0001_back.png   ->  0001_Charmander_9-25_back.png

The leading number is kept deliberately: it is the only thing tying a front to its
back, and OCR is not allowed to be the thing that breaks that.

Usage:
    cropdeck name sorted
    cropdeck name <folder> --dry-run        # show what it would do, change nothing
    cropdeck name <folder> --lang en        # use English names on German cards

Needs the Tesseract engine itself (pytesseract only talks to it):
    Windows -> https://github.com/UB-Mannheim/tesseract/wiki
    Linux   -> sudo apt install tesseract-ocr
    macOS   -> brew install tesseract
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

from . import manifest
from .imageio import IMAGE_EXTS, imread_unicode

try:
    import pytesseract
except ImportError:
    print('pytesseract is missing:  pip install "cropdeck[names]"', file=sys.stderr)
    raise

NAMES_FILE = Path(__file__).parent / "data" / "pokemon_names.json"
# Where the Windows installer puts Tesseract; it does not add itself to PATH by default.
# Installed for all users it lands in Program Files, for one user under LOCALAPPDATA\Programs.
WINDOWS_TESSERACT = [
    Path(os.environ.get("ProgramFiles", "C:\\Program Files"), "Tesseract-OCR", "tesseract.exe"),
    Path(os.environ.get("LOCALAPPDATA", "C:\\"), "Programs", "Tesseract-OCR", "tesseract.exe"),
]
TESSERACT_HELP = (
    "! The Tesseract engine is not installed or not on PATH - names cannot be read.\n"
    "  Windows: https://github.com/UB-Mannheim/tesseract/wiki (the default folder is found)\n"
    "  Linux:   sudo apt install tesseract-ocr      macOS: brew install tesseract"
)
# Only ever matches cropdeck split's raw output (card_0007_front). Once a file has been
# renamed to 0007_Snivy_5-25_front it no longer matches, so re-running this script
# leaves already-named cards alone instead of chewing them up a second time.
FRONT_RE = re.compile(r"^(?:card_)?(?P<num>\d{3,6})_front$", re.I)


# --------------------------------------------------------------------------
def norm(s: str) -> str:
    """Fold to bare lowercase letters so OCR noise and accents stop mattering."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.lower())


def load_names():
    if not NAMES_FILE.exists():
        print(f"! {NAMES_FILE.name} is missing from the cropdeck package", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
    index = {}
    for printed, english in raw.items():
        index.setdefault(norm(printed), (printed, english))
    return index


# --------------------------------------------------------------------------
def prep(band, upscale=2):
    """Make a colour band of card art readable: flatten the gradient, then binarise."""
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    # Pokemon name plates sit on a colour gradient. A global threshold swallows the
    # dark end of it; dividing by a heavily closed copy flattens the gradient first.
    bg = cv2.morphologyEx(
        g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
    )
    flat = cv2.divide(g, bg, scale=255)
    _, t = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # drop rows that are almost solid ink - that's the card border, not text
    keep = np.where((t == 0).mean(axis=1) < 0.55)[0]
    if len(keep):
        t = t[keep[0] : keep[-1] + 1]
    if t.size == 0:
        return None
    return cv2.copyMakeBorder(t, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=255)


def ocr_tokens(img, deadline=None):
    """All word-ish tokens tesseract can see, sparse-text mode."""
    out = []
    for psm in (11, 8):
        if deadline and time.monotonic() > deadline:
            break
        try:
            txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
        except Exception:
            continue
        out += re.split(r"[^0-9A-Za-zÀ-ÿ'.\-]+", txt)
    return [t for t in out if t]


def best_name(tokens, index, min_ratio: float):
    """Fuzzy-match OCR tokens against the Pokemon name list. Longest good hit wins."""
    best = None
    for tok in tokens:
        n = norm(tok)
        if len(n) < 4:  # 'Muk' style names are too easy to fake
            continue
        if n in index:
            printed, english = index[n]
            return printed, english, 1.0
        for key, (printed, english) in index.items():
            if abs(len(key) - len(n)) > 2:
                continue
            r = SequenceMatcher(None, key, n).ratio()
            if r >= min_ratio and (best is None or r > best[2]):
                best = (printed, english, r)
    return best if best else (None, None, 0.0)


NUM_BANDS = (
    (0.86, 0.99, 0.00, 0.50),  # older cards: bottom-left
    (0.86, 0.99, 0.50, 1.00),  # modern cards: bottom-right
    (0.86, 0.99, 0.00, 1.00),
)  # last resort: the whole bottom strip


def read_number(img, deadline=None):
    """
    Collector number like 9/25, 54/64 or 130/264, printed small at the bottom.

    Reads several bands and votes, because a single pass over small italic text
    misreads often enough to matter - '21/25' comes back as '2/25' about as readily
    as the truth. Bails out as soon as one reading is confirmed by a second.
    """
    H, W = img.shape[:2]
    votes = {}
    for y0, y1, x0, x1 in NUM_BANDS:
        if deadline and time.monotonic() > deadline:
            break
        p = prep(img[int(H * y0) : int(H * y1), int(W * x0) : int(W * x1)], upscale=3)
        if p is None:
            continue
        for psm in (11, 6):
            if deadline and time.monotonic() > deadline:
                break
            try:
                txt = pytesseract.image_to_string(p, config=f"--psm {psm}")
            except Exception:
                continue
            for m in re.finditer(r"(\d{1,3})\s*/\s*(\d{1,3})", txt):
                a, b = int(m.group(1)), int(m.group(2))
                if 1 <= a <= b and b >= 10:  # a real card number, not noise
                    key = f"{a}-{b}"
                    votes[key] = votes.get(key, 0) + 1
                    if votes[key] >= 2:
                        return key
    if not votes:
        return ""
    return max(votes.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def identify(path: Path, index, min_ratio: float, want_number: bool, budget: float):
    """
    Read one card. `budget` is a hard wall-clock ceiling in seconds: when it runs out
    we stop and return whatever we have, rather than grinding away at a card that has
    no readable name (Trainer and Energy cards, mostly). Half the budget goes to the
    name, the rest to the collector number.
    """
    img = imread_unicode(path)
    if img is None:
        return None, None, 0.0, ""
    start = time.monotonic()
    name_deadline = start + budget * 0.5 if budget else None
    H, W = img.shape[:2]
    tokens = []
    # two bands: modern cards put the name at the very top, older ones a little lower
    for y0, y1 in ((0.02, 0.105), (0.05, 0.16)):
        if name_deadline and time.monotonic() > name_deadline:
            break
        p = prep(img[int(H * y0) : int(H * y1), int(W * 0.06) : int(W * 0.82)])
        if p is not None:
            tokens += ocr_tokens(p, name_deadline)
    printed, english, ratio = best_name(tokens, index, min_ratio)
    number = ""
    if want_number and printed:
        number = read_number(img, start + budget if budget else None)
    return printed, english, ratio, number


# --------------------------------------------------------------------------
def safe(s: str) -> str:
    return re.sub(r"[^0-9A-Za-zÀ-ÿ.\-]+", "", s.replace(" ", ""))


def add_arguments(p: argparse.ArgumentParser):
    p.add_argument("folder", help="folder of cropped cards (cropdeck split output)")
    p.add_argument(
        "--lang",
        default="printed",
        choices=["printed", "en"],
        help="'printed' (default) = the name as it appears on the card; "
        "'en' = always the English name",
    )
    p.add_argument(
        "--min-ratio",
        type=float,
        default=0.82,
        help="how close OCR must get to a real name to count (default 0.82)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        metavar="SEC",
        help="give up on a card after this many seconds and call it "
        "'unknown' (default 15; 0 = no limit)",
    )
    p.add_argument(
        "--no-number", action="store_true", help="skip reading the collector number (faster)"
    )
    p.add_argument("--dry-run", action="store_true", help="print what would happen, rename nothing")


def find_tesseract() -> bool:
    """Point pytesseract at the Tesseract engine: PATH first, then the Windows install folder."""
    if shutil.which("tesseract"):
        return True
    found = next((p for p in WINDOWS_TESSERACT if p.is_file()), None)
    if found:
        pytesseract.pytesseract.tesseract_cmd = str(found)
    return found is not None


def run(args) -> int:
    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"! not a folder: {folder}", file=sys.stderr)
        return 1
    if not find_tesseract():
        print(TESSERACT_HELP, file=sys.stderr)
        return 1

    index = load_names()
    fronts = sorted(
        f
        for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS and FRONT_RE.match(f.stem)
    )
    if not fronts:
        print("No *_front images here. Run cropdeck split --pair first.", file=sys.stderr)
        return 1

    print(f"Reading {len(fronts)} card(s) in {folder}\n")
    rows, named, unknown = [], 0, []
    for f in fronts:
        m = FRONT_RE.match(f.stem)
        num = m.group("num")
        printed, english, ratio, number = identify(
            f, index, args.min_ratio, not args.no_number, args.timeout
        )
        label = (english if args.lang == "en" else printed) or ""

        parts = [num] + ([safe(label)] if label else ["unknown"])
        if number:
            parts.append(number)
        base = "_".join(parts)

        back = next(
            (
                b
                for b in folder.iterdir()
                if b.is_file() and b.stem == f.stem[: -len("front")] + "back"
            ),
            None,
        )

        flag = "" if label else "   <- not recognised, left as 'unknown'"
        conf = f"{ratio:.2f}" if label else "-"
        print(f"  {f.name:<28} -> {base}_front{f.suffix}   [{conf}]{flag}")
        if label:
            named += 1
        else:
            unknown.append(f.name)

        if not args.dry_run:
            f.rename(folder / f"{base}_front{f.suffix}")
            if back:
                back.rename(folder / f"{base}_back{back.suffix}")

        rows.append(
            {
                "card": num,
                "name": label,
                "name_en": english or "",
                "number": number.replace("-", "/") if number else "",
                "confidence": conf,
                "front": f"{base}_front{f.suffix}",
                "back": f"{base}_back{back.suffix}" if back else "",
            }
        )

    if not args.dry_run:
        # merge, never replace: a named card's row keeps every column this step does not
        # own (the split step's tray and slot, anything you typed in), and rows for
        # cards named in earlier runs are left alone
        by_card = {r.get("card"): r for r in manifest.read(folder)}
        for r in rows:
            by_card[r["card"]] = {**by_card.get(r["card"], {}), **r}
        merged = sorted(by_card.values(), key=lambda r: str(r.get("card", "")))
        out = manifest.write(folder, merged)
        print(f"\nManifest updated: {out}  ({len(merged)} card(s) total)")

    print(f"\n{named}/{len(fronts)} identified.")
    if unknown:
        print("Not recognised (Trainer/Energy cards have no Pokemon name - that's expected):")
        for u in unknown:
            print(f"  - {u}")
    if args.dry_run:
        print("\nDry run - nothing was renamed.")
    return 0
