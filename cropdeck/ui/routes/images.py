"""
The images the pages show: card thumbnails and downscaled scans of a tray.

No file path is taken from a URL. A card thumbnail is served only for a file name cards.csv (or
the run going on) lists as a card of this folder; a scan only by tray number and side, looked up
in the folder's trays.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ... import paths, trays
from ...manifest import read as read_manifest
from ...state import load_state
from .. import thumbs

CACHE_HEADERS = {"Cache-Control": "no-cache"}  # revalidate: a card file can be replaced


def register(app, work, runner):
    def sorted_dir():
        if work.folder is None:
            raise HTTPException(404)
        return work.folder / paths.SORTED

    def known_card(name: str) -> bool:
        p = runner.progress
        if p is not None and any(name in (f, r) for _, f, r in p.slots):
            return True
        return any(name in (r.get("front"), r.get("back")) for r in read_manifest(sorted_dir()))

    @app.get("/thumb/{name}")
    def card_thumb(name: str):
        out = sorted_dir()
        if "/" in name or "\\" in name or name.startswith(".") or not known_card(name):
            raise HTTPException(404)
        made = thumbs.card(out / name, out)
        if made is None:
            raise HTTPException(404)
        return FileResponse(made, media_type="image/jpeg", headers=CACHE_HEADERS)

    @app.get("/tray/{n}/scan/{side}.jpg")
    def tray_scan(n: int, side: str):
        out = sorted_dir()
        folder = trays.build(
            trays.scans_in(work.folder / paths.SCANS), load_state(out), read_manifest(out)
        )
        if side not in ("front", "back") or not 1 <= n <= len(folder):
            raise HTTPException(404)
        src = folder[n - 1].front if side == "front" else folder[n - 1].back
        made = thumbs.scan(src, out) if src else None
        if made is None:
            raise HTTPException(404)
        return FileResponse(made, media_type="image/jpeg", headers=CACHE_HEADERS)
