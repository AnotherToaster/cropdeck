"""
A folder's trays: which scan holds which tray's fronts and backs, and how far each tray is.

Scans pair in name order - the first scan is tray 1's fronts, the second its backs, and so on.
A fix chosen for a tray can take a scan out of that order: a rescan assigns the next new scan as
the tray's backs, and an unusable backs scan is marked unused. Those choices live in the state
file (state["trays"]), never in the scans themselves, which are only ever read.

Shared by `cropdeck split --pair`, `cropdeck status` and the browser interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .imageio import IMAGE_EXTS
from .state import scan_key

DONE, READY, NEEDS_BACKS, STOPPED, SKIPPED = "done", "ready", "needs-backs", "stopped", "skipped"


@dataclass
class Tray:
    n: int
    front: Path
    back: Path | None
    status: str
    cards: tuple[int, int] | None = None  # first and last card number, once done
    stop: dict | None = None  # why it stopped: kind, message, detail
    awaiting: bool = False  # its backs are to be rescanned

    @property
    def keys(self) -> list[str]:
        return [scan_key(self.front), scan_key(self.back) if self.back else ""]


def scans_in(folder: Path) -> list[Path]:
    """The scans in a folder, sorted by name - the order trays pair in."""
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)


def choices(state: dict, n: int) -> dict:
    """The fixes chosen for tray n (empty if none); stored in the state file."""
    return state.setdefault("trays", {}).setdefault(str(n), {})


def _assigned(files: list[Path], state: dict) -> dict[int, Path]:
    """Tray number -> the scan assigned as its backs. A tray waiting for a rescan takes the first
    scan named after the newest one there was when the rescan was chosen."""
    by_name = {f.name: f for f in files}
    out: dict[int, Path] = {}
    taken: set[str] = set()
    trays = state.get("trays", {})
    for n, c in sorted(trays.items(), key=lambda kv: int(kv[0])):
        if c.get("back") in by_name:
            out[int(n)] = by_name[c["back"]]
            taken.add(c["back"])
    for n, c in sorted(trays.items(), key=lambda kv: int(kv[0])):
        after = c.get("await_after")
        if after is None or int(n) in out:
            continue
        unused = set(c.get("unused", []))
        for f in files:
            if f.name > after and f.name not in taken and f.name not in unused:
                out[int(n)] = f
                taken.add(f.name)
                break
    return out


def _card_ranges(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """Scan name -> (first, last) card number cut from it, from the cards.csv rows."""
    out: dict[str, tuple[int, int]] = {}
    for r in rows:
        try:
            no = int(r.get("card") or "")
        except ValueError:
            continue
        for scan in (r.get("scan_front"), r.get("scan_back")):
            if scan:
                lo, hi = out.get(scan, (no, no))
                out[scan] = (min(lo, no), max(hi, no))
    return out


def build(files: list[Path], state: dict, rows: list[dict]) -> list[Tray]:
    """Every tray of the folder, in order. files: the scans, sorted by name."""
    trays_state = state.get("trays", {})
    assigned = _assigned(files, state)
    unused = {name for c in trays_state.values() for name in c.get("unused", [])}
    skip = {f.name for f in assigned.values()} | unused
    sequence = [f for f in files if f.name not in skip]
    ranges = _card_ranges(rows)

    out: list[Tray] = []
    i = 0
    while i < len(sequence):
        n = len(out) + 1
        c = trays_state.get(str(n), {})
        front = sequence[i]
        i += 1
        if n in assigned:
            back = assigned[n]
        elif c.get("await_after") is not None:
            back = None  # the old backs are not used; the rescan has not arrived yet
        elif i < len(sequence):
            back = sequence[i]
            i += 1
        else:
            back = None
        tray = Tray(n, front, back, READY, awaiting=c.get("await_after") is not None)
        stop = c.get("stop")
        if scan_key(front) in state.get("done", {}):
            tray.status = DONE
            tray.cards = ranges.get(front.name) or (ranges.get(back.name) if back else None)
        elif c.get("skip"):
            tray.status = SKIPPED
        elif back is None:
            tray.status = NEEDS_BACKS
        elif stop and stop.get("keys") == tray.keys:
            tray.status, tray.stop = STOPPED, stop
        out.append(tray)
    return out


def next_up(trays: list[Tray]) -> Tray | None:
    """The tray the next run starts with or waits on: the first neither done nor skipped."""
    return next((t for t in trays if t.status not in (DONE, SKIPPED)), None)


def runnable(trays: list[Tray]) -> list[Tray]:
    """The trays a run processes now: ready ones, in order, up to the first that blocks
    (stopped, or waiting for its backs). Skipped trays are passed over."""
    out = []
    for t in trays:
        if t.status in (DONE, SKIPPED):
            continue
        if t.status != READY:
            break
        out.append(t)
    return out
