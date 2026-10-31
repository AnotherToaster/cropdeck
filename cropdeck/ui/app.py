"""
The FastAPI app behind `cropdeck ui`: server-rendered pages (Jinja2) and their static files.

It only ever answers the browser on this computer (or, with `cropdeck ui --host`, on the one
address it was bound to). Two checks enforce that beyond the bind: the Host header must name this
server (a foreign host is a DNS-rebinding attempt), and a
request that changes something must not come from a foreign Origin (another website posting to
it). Requests that change state are never GETs, so a link or an image elsewhere cannot trigger one.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import paths
from . import i18n, live, review_view, session
from .routes import images, pages, review, scan, setup, stop
from .runner import Runner

HERE = Path(__file__).resolve().parent
HEALTH = "cropdeck ok"  # what /health answers; the launcher recognises a running cropdeck by it
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
THEMES = {"light", "dark"}


def create_app(
    port: int,
    *,
    dev: bool = False,
    hosts: tuple[str, ...] = (),
    work: session.Session | None = None,
    watch: bool = True,
    address: str | None = None,
) -> FastAPI:
    """The app for a server on 127.0.0.1:port. dev adds the design-check helpers; hosts adds
    host names to accept besides 127.0.0.1 and localhost (the tests' client); work is the folder
    and layout to show (none: setup first); watch polls the scans folder for new scans; address
    ("100.64.0.1:8737") is the one other address the server is bound to (`cropdeck ui --host`)."""
    hub = live.Hub()
    runner = Runner(hub)

    @asynccontextmanager
    async def lifespan(_app):
        def scans():
            return work.folder / paths.SCANS if work.folder else None

        task = asyncio.create_task(live.watch(scans, hub)) if watch else None
        yield
        if task:
            task.cancel()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", *hosts}
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    if address:
        allowed.add(address)
        origins.add(f"http://{address}")
    work = work or session.Session(None, session.LAYOUTS[session.DEFAULT])

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

    def render(request: Request, template: str, **context) -> HTMLResponse:
        # dev only: ?theme=dark|light forces a theme, for screenshots against the design
        theme = request.query_params.get("theme") if dev else None
        context.update(
            lang=i18n.DEFAULT,
            theme=theme if theme in THEMES else None,
            work=work,
            review_count=review_view.needs_look(work.folder),
        )
        return templates.TemplateResponse(request, template, context)

    def fragment(template: str, names, *args, **kw) -> str:
        """Macros of a partial template, rendered one after another (for htmx and SSE)."""
        module = templates.env.get_template(template).make_module({"lang": i18n.DEFAULT})
        return "".join(str(getattr(module, name)(*args, **kw)) for name in names)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return HEALTH

    app.state.fragment = fragment  # the tests render event parts through it
    pages.register(app, render, work, HERE / "static", dev=dev)
    scan.register(app, render, fragment, work, hub, runner)
    stop.register(app, render, work, hub, runner)
    setup.register(app, render, fragment, work, runner)
    review.register(app, render, fragment, work)
    images.register(app, work, runner)
    return app
