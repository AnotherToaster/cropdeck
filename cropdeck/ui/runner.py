"""
Processing from the browser: one run at a time, in a worker thread (cutting cards is CPU-bound
OpenCV work and must not hold up the server). The run is the same process.run() the command line
uses; this only keeps track of how far it is, for the page, and publishes each event to the hub.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths, process, split, trays
from ..manifest import read as read_manifest
from ..state import load_state
from . import thumbs
from .live import Hub


@dataclass
class Progress:
    """The run as the page shows it. Card counts per tray are the layout's until the tray's own
    detection says otherwise."""

    trays: list[int]  # tray numbers in this run, in order
    expected: int  # cards per tray from the layout
    current: int = 0  # index into trays
    done: dict[int, int] = field(default_factory=dict)  # tray -> cards written
    counts: dict[int, int] = field(default_factory=dict)  # tray -> cards it holds
    slots: list[tuple[int, str, str]] = field(default_factory=list)  # current tray's cards
    halt: bool = False  # "stop after this tray" was asked

    @property
    def tray(self) -> int:
        return self.trays[self.current]

    def count(self, n: int) -> int:
        return self.counts.get(n, self.expected)


class Runner:
    def __init__(self, hub: Hub):
        self.hub = hub
        self.progress: Progress | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.progress is not None

    def start(self, folder: Path, expected: int) -> bool:
        """Start processing the folder's runnable trays. False if a run is going already or
        there is nothing to process."""
        with self._lock:
            if self.progress is not None:
                return False
            out = folder / paths.SORTED
            state = load_state(out)
            todo = trays.runnable(
                trays.build(trays.scans_in(folder / paths.SCANS), state, read_manifest(out))
            )
            if not todo:
                return False
            self.progress = Progress([t.n for t in todo], expected)
        opts = split.options(expect=expected)
        threading.Thread(
            target=self._work, args=(todo, opts, state, out), name="cropdeck-run", daemon=True
        ).start()
        self.hub.publish("run-start")
        return True

    def halt(self) -> None:
        """Finish the tray being cut, then stop."""
        if self.progress is not None:
            self.progress.halt = True
            self.hub.publish("run-halting")

    def _work(self, todo, opts, state, out: Path) -> None:
        p = self.progress
        out.mkdir(parents=True, exist_ok=True)
        try:
            for event in process.run(todo, opts, state, out, halt=lambda: p.halt):
                if isinstance(event, process.CardDone):  # ready before the page asks for them
                    thumbs.card(out / event.front, out)
                    thumbs.card(out / event.rear, out)
                self._track(p, event)
        finally:
            with self._lock:
                self.progress = None
            self.hub.publish("run-done")

    def _track(self, p: Progress, event) -> None:
        if isinstance(event, process.TrayStart):
            p.current = p.trays.index(event.tray.n)
            p.slots = []
            self.hub.publish("tray-start", tray=event.tray.n)
        elif isinstance(event, process.CardDone):
            p.counts[event.tray.n] = event.count
            p.done[event.tray.n] = event.index
            p.slots.append((event.card, event.front, event.rear))
            self.hub.publish("card-done", tray=event.tray.n, card=event.card)
        elif isinstance(event, process.TrayDone):
            self.hub.publish("tray-done", tray=event.tray.n)
        elif isinstance(event, process.TrayStopped):
            self.hub.publish("tray-stopped", tray=event.tray.n, kind=event.kind)
