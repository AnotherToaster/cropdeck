"""
The guard stops (`/tray/{n}/stop`): why a tray was refused, and its fixes. A fix is a choice
written to the state file (cropdeck/fixes.py) - no scan is renamed, moved or deleted - after which
the page goes back to the scan loop and the queued trays run again where they can.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import fixes, paths, trays
from ...manifest import read as read_manifest
from ...state import load_state
from .. import stop_view
from .scan import change_tray

# action in the URL -> what it records; action(state, tray, scans)
ACTIONS = {
    "rescan": lambda state, tray, files: fixes.rescan(state, tray, files),
    "forgot": lambda state, tray, files: fixes.rescan(state, tray, files, keep_old=True),
    "pairs_only": lambda state, tray, files: fixes.pairs_only(state, tray.n),
    "new_back": lambda state, tray, files: fixes.new_back(state, tray.n),
    "swap": lambda state, tray, files: fixes.swap(state, tray.n),
    "keep": lambda state, tray, files: fixes.keep(state, tray.n),
    "skip": lambda state, tray, files: fixes.skip(state, tray.n),
}


def register(app, render, work, hub, runner):
    def folder() -> list[trays.Tray]:
        out = work.folder / paths.SORTED
        files = trays.scans_in(work.folder / paths.SCANS)
        return trays.build(files, load_state(out), read_manifest(out))

    @app.get("/tray/{n}/stop")
    def stop(request: Request, n: int):
        if work.folder is None:
            return RedirectResponse("/setup", status_code=303)
        all_trays = folder()
        if not 1 <= n <= len(all_trays):
            raise HTTPException(404, f"There is no tray {n}.")
        tray = all_trays[n - 1]
        if tray.status != trays.STOPPED:  # fixed or skipped meanwhile: nothing to show
            return RedirectResponse("/", status_code=303)
        return render(
            request, "pages/stop.html", current="scan", s=stop_view.build(tray, all_trays)
        )

    @app.post("/tray/{n}/fix/{action}")
    def fix(n: int, action: str):
        if action not in ACTIONS:
            raise HTTPException(404, f"There is no fix {action!r}.")
        change_tray(work, runner, hub, n, ACTIONS[action])
        # the queued trays run again where they can; a rescan waits for its new scan
        runner.start(work.folder, work.layout.count)
        return RedirectResponse("/", status_code=303)
