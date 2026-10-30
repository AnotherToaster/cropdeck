"""
The FastAPI app behind `cropdeck ui`: server-rendered pages (Jinja2) and their static files.

It only ever answers the browser on this computer. Two checks enforce that beyond the 127.0.0.1
bind: the Host header must name this server (a foreign host is a DNS-rebinding attempt), and a
request that changes something must not come from a foreign Origin (another website posting to
it). Requests that change state are never GETs, so a link or an image elsewhere cannot trigger one.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import i18n

HERE = Path(__file__).resolve().parent
HEALTH = "cropdeck ok"  # what /health answers; the launcher recognises a running cropdeck by it
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
THEMES = {"light", "dark"}


def create_app(port: int, *, dev: bool = False, hosts: tuple[str, ...] = ()) -> FastAPI:
    """The app for a server on 127.0.0.1:port. dev adds the design-check helpers; hosts adds
    host names to accept besides 127.0.0.1 and localhost (the tests' client)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", *hosts}
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["t"] = i18n.t
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        if request.headers.get("host", "") not in allowed:
            return PlainTextResponse("This cropdeck only answers its own address.", 421)
        origin = request.headers.get("origin")
        if request.method not in SAFE_METHODS and origin and origin not in origins:
            return PlainTextResponse("Requests from other websites are refused.", 403)
        return await call_next(request)

    def page(request: Request, template: str, **context) -> HTMLResponse:
        # dev only: ?theme=dark|light forces a theme, for screenshots against the design
        theme = request.query_params.get("theme") if dev else None
        context.update(lang=i18n.DEFAULT, theme=theme if theme in THEMES else None)
        return templates.TemplateResponse(request, template, context)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return HEALTH

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "base.html")

    return app
