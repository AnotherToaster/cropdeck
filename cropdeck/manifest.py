"""
cards.csv: one row per card, written by the split and name steps and read by track.

Every writer merges rather than replaces: rows already in the file survive, and so does
any column another step added or the user typed in. Columns are written base fields
first, then everything else in the order it was first seen.
"""

from __future__ import annotations

import csv
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
    """Write rows to folder/cards.csv, keeping every column any row carries."""
    path = folder / FILE
    fields = list(BASE_FIELDS)
    for r in rows:
        for k in r:
            if k and k not in fields:
                fields.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in fields}, **{k: v for k, v in r.items() if k}})
    return path
