"""
What the scan loop shows, worked out on the server from the folder itself (and the run, while one
goes): exactly one of six states, the trays newest first, and the two numbers in the sidebar.
Templates only lay this out; they decide nothing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths, trays
from ..layouts import Layout
from ..manifest import read as read_manifest
from ..state import load_state
from .i18n import t
from .runner import Progress
from .thumbs import thumb_url

EMPTY, FLIP, READY, PROCESSING, STOPPED, DONE = (
    "empty",
    "flip",
    "ready",
    "processing",
    "stopped",
    "done",
)
PER_PAGE = 20


@dataclass
class Pic:
    """A card as the pages draw it: number and the URLs of its two thumbnails."""

    number: str
    front: str
    back: str
    state: str = "done"  # in the run's slots: done, working, pending


@dataclass
class Row:
    """One tray in the list: its badge kind, and what is under its head line."""

    tray: trays.Tray
    kind: str  # badge: done, ready, needs-backs, stopped, skipped, working, waiting
    note: str | None = None  # text key under the head line
    note_values: dict | None = None
    pairs: list | None = None  # Pic per card when expanded
    strip: list | None = None  # thumbnail URLs of the fronts when collapsed
    time: str | None = None


@dataclass
class View:
    state: str
    folder: Path
    trays: list[trays.Tray]
    rows: list[Row]
    page: int
    pages: int
    cards_so_far: int
    next_card: int
    focus: trays.Tray | None  # the tray the next step is about
    ready: list[trays.Tray]
    progress: Progress | None
    layout: Layout
    focus_time: str | None = None  # when the fronts scan of the tray in focus was saved
    segments: list = field(default_factory=list)  # the run's progress, one per tray
    slots: list = field(default_factory=list)  # the run's current tray, one Pic per card

    @property
    def expected(self) -> int:
        return self.layout.count

    @property
    def scans(self) -> Path:
        return self.folder / paths.SCANS


def _clock(path: Path) -> str | None:
    try:
        return time.strftime("%H:%M", time.localtime(path.stat().st_mtime))
    except OSError:
        return None


def build(folder: Path, layout: Layout, progress: Progress | None, page: int = 1) -> View:
    out = folder / paths.SORTED
    state = load_state(out)
    rows_csv = read_manifest(out)
    all_trays = trays.build(trays.scans_in(folder / paths.SCANS), state, rows_csv)
    nxt = trays.next_up(all_trays)
    ready = trays.runnable(all_trays)

    if progress is not None:
        st = PROCESSING
    elif not all_trays:
        st = EMPTY
    elif nxt is None:
        st = DONE
    elif nxt.status == trays.STOPPED:
        st = STOPPED
    elif nxt.status == trays.NEEDS_BACKS and not ready:
        st = FLIP
    else:
        st = READY

    cards = {}
    for r in rows_csv:
        cards.setdefault(r.get("scan_front"), []).append(r)
    rows = [_row(t, st, nxt, progress, cards, out) for t in reversed(all_trays)]
    latest_done = next((r for r in rows if r.kind == "done"), None)
    for r in rows:
        if r.kind == "done" and r is not latest_done:
            r.strip, r.pairs = [p.front for p in r.pairs or []], None
    pages = max(1, -(-len(rows) // PER_PAGE))
    page = min(max(page, 1), pages)

    done_cards = sum(t.cards[1] - t.cards[0] + 1 for t in all_trays if t.cards)
    # the tray being cut is on disk card by card, but in the manifest and state only once done
    current = progress and next((t for t in all_trays if t.n == progress.tray), None)
    partial = progress.done.get(progress.tray, 0) if current and current.status != trays.DONE else 0
    view = View(
        state=st,
        folder=folder,
        trays=all_trays,
        rows=rows[(page - 1) * PER_PAGE : page * PER_PAGE],
        page=page,
        pages=pages,
        cards_so_far=done_cards + partial,
        next_card=state.get("next", 1) + partial,
        focus=nxt,
        ready=ready,
        progress=progress,
        layout=layout,
        focus_time=_clock(nxt.front) if nxt else None,
    )
    if progress is not None:
        view.segments = _segments(progress)
        view.slots = _slots(progress, view.next_card)
    return view


def _no(n: int) -> str:
    return f"{n:04d}"


def _segments(p: Progress) -> list[dict]:
    out = []
    for k, n in enumerate(p.trays):
        done, count = p.done.get(n, 0), p.count(n)
        if k < p.current:
            out.append({"fill": 1.0, "label": t("scan.seg_done", n=n)})
        elif k == p.current:
            out.append(
                {
                    "fill": done / count if count else 0.0,
                    "label": t("scan.seg_working", n=n, done=done, count=count),
                }
            )
        else:
            out.append({"fill": 0.0, "label": t("scan.seg_waiting", n=n)})
    return out


def _slots(p: Progress, next_card: int) -> list[Pic]:
    """The current tray's cards: those written show their thumbnails, the next one is being cut,
    the rest are to come."""
    done = [Pic(_no(no), thumb_url(f), thumb_url(r)) for no, f, r in p.slots]
    first = next_card - len(done)
    rest = [
        Pic(_no(first + k), "", "", "working" if k == len(done) else "pending")
        for k in range(len(done), p.count(p.tray))
    ]
    return done + rest


def _row(t, st, nxt, progress, cards, out: Path) -> Row:
    if progress is not None and t.n in progress.trays and t.status != trays.DONE:
        if t.n == progress.tray:
            return Row(t, "working", "tray.note_working")
        return Row(t, "waiting", "tray.note_next")
    if t.status == trays.DONE:
        found = sorted(
            (r["card"], r["front"], r["back"])
            for r in cards.get(t.front.name, []) + cards.get(t.back.name if t.back else "", [])
            if r.get("front") and r.get("back")
        )
        pairs = [Pic(_no(int(no)), thumb_url(f), thumb_url(b)) for no, f, b in found]
        last = out / found[-1][2] if found else None
        return Row(t, "done", pairs=pairs, time=_clock(last) if last else None)
    if t.status == trays.SKIPPED:
        return Row(t, "skipped", "tray.note_skipped")
    if t.status == trays.STOPPED:
        return Row(t, "stopped", "stop.row." + t.stop["kind"], t.stop.get("detail"))
    if t.status == trays.NEEDS_BACKS:
        return Row(t, "needs-backs", "tray.note_rescan" if t.awaiting else "tray.note_flip")
    if nxt is not None and nxt.n < t.n and nxt.status in (trays.STOPPED, trays.NEEDS_BACKS):
        return Row(t, "waiting", "tray.note_waiting_for", {"n": nxt.n})
    return Row(t, "ready", "tray.note_ready")
