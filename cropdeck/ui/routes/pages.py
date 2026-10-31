"""
The pages of the shell. Each screen is filled in by its phase (handoff: scan loop 3, setup 5,
review 6, collection 7, settings 8); until then it is its title inside the shell. Also the two
files the installed app window (PWA) needs at the site root.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse


def register(app, render, work, static: Path):
    def screen(request: Request, current: str):
        return render(request, "pages/placeholder.html", current=current)

    @app.get("/")
    def scan(request: Request):
        if work.folder is None:  # first start: set up a folder before anything else
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"/setup{query}", status_code=303)
        return screen(request, "scan")

    @app.get("/review")
    def review(request: Request):
        return screen(request, "review")

    @app.get("/collection")
    def collection(request: Request):
        return screen(request, "collection")

    @app.get("/settings")
    def settings(request: Request):
        return screen(request, "settings")

    @app.get("/setup")
    def setup(request: Request):
        return render(request, "pages/setup.html", current=None)

    @app.get("/offline")
    def offline(request: Request):
        return render(request, "pages/offline.html", current=None)

    # the service worker must be served from the root to look after the whole site
    @app.get("/sw.js")
    def service_worker():
        return FileResponse(static / "sw.js", media_type="text/javascript")

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(static / "manifest.webmanifest", media_type="application/manifest+json")
