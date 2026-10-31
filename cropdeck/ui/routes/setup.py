"""
Setup (`/setup`): which folder holds this collection and how the cards lie on its glass. Shown
first when no folder is set up yet, and again whenever the folder or layout is to change.

The folder is picked in the page itself (cropdeck/ui/folders.py lists the folders through the
server), so it works the same on every system and in the bundled app.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import paths
from ...layouts import DEFAULT, LAYOUTS
from .. import folders, forms, session, wsl

PARTIAL = "partials/setup.html"


@dataclass
class SetupView:
    folder: str  # as typed, so a refused path stays in the field
    layout: str  # layout id
    error: str | None = None  # text key, shown under the folder field

    @property
    def scans(self) -> str:
        """Where the scanner saves to, for the path box; empty until the path is absolute."""
        typed = wsl.from_windows(self.folder.strip())
        p = Path(typed).expanduser() if typed else None
        return str(p / paths.SCANS) if p and p.is_absolute() else ""

    @property
    def layouts(self):
        return LAYOUTS.values()

    default = DEFAULT


def register(app, render, fragment, work, runner):
    def page(request: Request, v: SetupView, status: int = 200) -> HTMLResponse:
        r = render(request, "pages/setup.html", current="setup", v=v)
        r.status_code = status
        return r

    @app.get("/setup")
    def setup(request: Request):
        folder = str(work.folder) if work.folder else ""
        return page(request, SetupView(folder, work.layout.id))

    @app.post("/setup")
    async def save(request: Request):
        form = await forms.read(request)
        v = SetupView(form.get("folder", ""), form.get("layout", ""))
        if v.layout not in LAYOUTS:
            v.layout = work.layout.id
        if runner.running:
            v.error = "setup.error.running"
            return page(request, v, 409)
        folder, v.error = folders.prepare(v.folder)
        if folder is None:
            return page(request, v, 422)
        session.choose(work, folder, LAYOUTS[v.layout])
        return RedirectResponse("/", status_code=303)

    @app.get("/setup/save-to", response_class=HTMLResponse)
    def save_to(folder: str = ""):
        return fragment(PARTIAL, ("save_to",), SetupView(folder, work.layout.id))

    @app.get("/setup/browse", response_class=HTMLResponse)
    def browse(folder: str = "", new: bool = False):
        return fragment(PARTIAL, ("browser",), folders.listing(folder), new=new)

    @app.post("/setup/browse/new", response_class=HTMLResponse)
    async def new_folder(request: Request):
        form = await forms.read(request)
        made, error = folders.make(form.get("parent", ""), form.get("name", ""))
        if made is None:
            shown = folders.listing(form.get("parent", ""))
            shown.error = shown.error or error
            return fragment(PARTIAL, ("browser",), shown, new=True, name=form.get("name", ""))
        return fragment(PARTIAL, ("browser",), folders.listing(str(made)))
