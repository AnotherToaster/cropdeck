"""
The pages of the shell. Each screen is filled in by its phase (handoff: collection 7,
settings 8); until then it is its title inside the shell. The scan loop has its
own module (routes/scan.py). Also the two
files the installed app window (PWA) needs at the site root.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse


def register(app, render, work, static: Path, dev: bool = False):
    def screen(request: Request, current: str):
        return render(request, "pages/placeholder.html", current=current)

    @app.get("/review")
    def review(request: Request):
        return screen(request, "review")

    @app.get("/collection")
    def collection(request: Request):
        return screen(request, "collection")

    @app.get("/settings")
    def settings(request: Request):
        return screen(request, "settings")

    @app.get("/offline")
    def offline(request: Request):
        return render(request, "pages/offline.html", current=None)

    @app.get("/_components")
    def components(request: Request):
        if not dev:  # a design-check page, not part of the app
            raise HTTPException(404)
        from ...layouts import LAYOUTS
        from .. import dev as samples

        return render(
            request, "pages/components.html", current=None, layouts=LAYOUTS, **samples.sample()
        )

    # the service worker must be served from the root to look after the whole site
    @app.get("/sw.js")
    def service_worker():
        return FileResponse(static / "sw.js", media_type="text/javascript")

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(static / "manifest.webmanifest", media_type="application/manifest+json")
