"""
Live updates for open pages: a hub that hands events to every server-sent-events stream, and the
watcher that notices new scans.

Events are names only ("card-done", "scans-changed", ...). What a page shows is rendered fresh
from the folder for each one, so a page can never show a stale state as current - a missed event
costs nothing but a moment.

Events may be published from any thread (the processing runs in a worker thread); each stream
reads them on the server's event loop.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

POLL_SECONDS = 2.0
KEEPALIVE_SECONDS = 15.0


class Hub:
    def __init__(self):
        self._queues: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self) -> asyncio.Queue:
        self._loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def publish(self, name: str, **data) -> None:
        """Hand an event to every open stream; safe to call from any thread."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for q in list(self._queues):
            loop.call_soon_threadsafe(q.put_nowait, (name, data))


def signature(folder: Path) -> tuple:
    """What changes when a scan is added, replaced or removed: names, sizes, times."""
    try:
        with os.scandir(folder) as it:
            return tuple(
                sorted((e.name, e.stat().st_size, e.stat().st_mtime_ns) for e in it if e.is_file())
            )
    except OSError:
        return ()


async def watch(folder_of, hub: Hub, interval: float = POLL_SECONDS) -> None:
    """Poll the scans folder (folder_of() names it; it may change after setup) and publish
    "scans-changed" when its files do. Polling, not file-system events: it needs no extra
    package and behaves the same on Windows, macOS, Linux and network drives."""
    last = None
    while True:
        folder = folder_of()
        now = signature(folder) if folder else ()
        if last is not None and now != last:
            hub.publish("scans-changed")
        last = now
        await asyncio.sleep(interval)


def sse(name: str, html: str) -> str:
    """One server-sent event; every line of the payload gets its own data: field."""
    lines = html.splitlines() or [""]
    return f"event: {name}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"
