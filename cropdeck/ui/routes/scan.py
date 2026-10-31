"""
The scan loop (`/`): the page, its live updates over server-sent events, and the three things it
can change - start processing, stop after the current tray, skip a refused tray (or take a
skipped one back).

Every answer to htmx is the affected parts of the page, rendered fresh from the folder; without
htmx (no JavaScript) a form posts and the browser is sent back to `/`.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse

from ... import fixes, paths, trays
from ...manifest import read as read_manifest
from ...state import load_state, save_state
from .. import live, scan_view

PARTIAL = "partials/scan.html"
PAGE_PARTS = ("failure", "next_step", "trays", "stats")
# what each event changes on the page; anything not listed changes the whole next step
EVENT_PARTS = {
    "card-done": ("run_head", "run_progress", "slots", "stats"),
    "run-halting": ("halt_control",),
}


def change_tray(work, runner, hub, n: int, action) -> None:
    """Record a choice for tray n in the state file: action(state, tray, scans). Refused while a
    run is going (the run writes the same file) and for a tray that does not exist."""
    if work.folder is None:
        raise HTTPException(409, "No cards folder is set up yet.")
    if runner.running:
        raise HTTPException(409, "A run is going. Wait until it is done.")
    out = work.folder / paths.SORTED
    state = load_state(out)
    files = trays.scans_in(work.folder / paths.SCANS)
    folder = trays.build(files, state, read_manifest(out))
    if not 1 <= n <= len(folder):
        raise HTTPException(404, f"There is no tray {n}.")
    action(state, folder[n - 1], files)
    out.mkdir(parents=True, exist_ok=True)
    save_state(out, state)
    hub.publish("scans-changed")


def register(app, render, fragment, work, hub, runner):
    def view(page: int = 1) -> scan_view.View:
        return scan_view.build(work.folder, work.layout, runner.progress, page, runner.failure)

    def parts(names, page: int = 1) -> str:
        return fragment(PARTIAL, names, view(page), oob=True)

    def answer(request: Request, names=PAGE_PARTS) -> Response:
        if request.headers.get("hx-request"):
            return HTMLResponse(parts(names))
        return RedirectResponse("/", status_code=303)

    def need_folder():
        if work.folder is None:
            raise HTTPException(409, "No cards folder is set up yet.")

    @app.get("/")
    def scan(request: Request, page: int = 1):
        if work.folder is None:  # first start: set up a folder before anything else
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"/setup{query}", status_code=303)
        return render(request, "pages/scan.html", current="scan", v=view(page))

    @app.get("/events")
    async def events(request: Request, page: int = 1):
        need_folder()
        queue = hub.subscribe()

        async def stream():
            try:
                # first a full refresh: a page that reconnects never keeps showing an old state
                yield live.sse("scans-changed", parts(PAGE_PARTS, page))
                while not await request.is_disconnected():
                    try:
                        name, _data = await asyncio.wait_for(queue.get(), live.KEEPALIVE_SECONDS)
                    except asyncio.TimeoutError:  # noqa: UP041 - Python 3.10 has its own
                        yield ": keep-alive\n\n"
                        continue
                    yield live.sse(name, parts(EVENT_PARTS.get(name, PAGE_PARTS), page))
            finally:
                hub.unsubscribe(queue)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/process")
    def process(request: Request):
        need_folder()
        runner.start(work.folder, work.layout.count)
        return answer(request)

    @app.post("/stop-after")
    def stop_after(request: Request):
        runner.halt()
        return answer(request, ("halt_control",) if runner.running else PAGE_PARTS)

    @app.post("/tray/{n}/skip")
    def skip(request: Request, n: int):
        change_tray(work, runner, hub, n, lambda state, tray, files: fixes.skip(state, n))
        runner.start(work.folder, work.layout.count)  # the trays behind it run, as after any fix
        return answer(request)

    @app.post("/tray/{n}/unskip")
    def unskip(request: Request, n: int):
        change_tray(work, runner, hub, n, lambda state, tray, files: fixes.unskip(state, n))
        return answer(request)
