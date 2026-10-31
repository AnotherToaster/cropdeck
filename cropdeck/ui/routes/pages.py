"""
The dev-only components page, the offline page, and the two files the installed app window (PWA)
needs at the site root. Scan, stop, setup and review have their own modules; collection and
settings (handoff phases 7 and 8) are not built yet, and the settings icon opens setup meanwhile.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse


def register(app, render, work, static: Path, dev: bool = False):
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
