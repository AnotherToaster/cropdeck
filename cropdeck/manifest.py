"""
cards.csv: one row per card, written by the split and name steps and read by track.

Every writer merges rather than replaces: rows already in the file survive, and so does
any column another step added or the user typed in. Columns are written base fields
first, then everything else in the order it was first seen.

What the user typed (in the review) is listed in the row's "typed" column, and recognition
never writes over those fields again. Inside one process - the browser interface, whose run and
review both write the file - every change goes through one lock, so neither loses the other's.
"""

from __future__ import annotations

import csv
import os
import threading
from pathlib import Path

FILE = "cards.csv"
BASE_FIELDS = [
    "card",
    "front",
    "back",
    "scan_front",
    "scan_back",
    "position",
    "name",
    "set",
    "number",
    "condition",
    "price",
    "notes",
]
TYPED = "typed"  # the fields the user typed in, space-separated
_lock = threading.Lock()


def read(folder: Path) -> list[dict]:
    """Every non-empty row of folder/cards.csv; an empty list if there is none yet."""
    path = folder / FILE
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [r for r in csv.DictReader(fh) if any(v for v in r.values())]
    except OSError:
        return []


def write(folder: Path, rows: list[dict]) -> Path:
    """Write rows to folder/cards.csv, keeping every column any row carries. The file is
    replaced in one step, so a reader never sees half of it."""
    path = folder / FILE
    fields = list(BASE_FIELDS)
    for r in rows:
        for k in r:
            if k and k not in fields:
                fields.append(k)
    # a name of its own per writer: the CLI and the UI may write one folder at the same time
    part = path.with_name(f".{path.name}.{os.getpid()}-{threading.get_ident()}.part")
    with open(part, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in fields}, **{k: v for k, v in r.items() if k}})
    os.replace(part, path)
    return path


def append(folder: Path, rows: list[dict]) -> Path:
    """Add rows after the ones already in the file."""
    with _lock:
        return write(folder, read(folder) + rows)


def typed(row: dict) -> set[str]:
    return set((row.get(TYPED) or "").split())


def update(folder: Path, card: str, values: dict[str, str]) -> dict | None:
    """Set fields of one card's row as the user typed them, and mark them typed (a value equal
    to the stored one is no edit). The row as it now is, or None for a card not in the file."""
    with _lock:
        rows = read(folder)
        row = next((r for r in rows if r.get("card") == card), None)
        if row is None:
            return None
        changed = {k for k, v in values.items() if (row.get(k) or "") != v}
        row.update(values)
        if changed - {"accepted"}:
            row[TYPED] = " ".join(sorted(typed(row) | (changed - {"accepted"})))
        write(folder, rows)
        return row


def recognised(row: dict, found: dict) -> dict:
    """row with what recognition found, except the fields the user typed in."""
    keep = typed(row)
    return {**row, **{k: v for k, v in found.items() if k not in keep}}
