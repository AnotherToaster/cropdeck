"""
cropdeck ui - start the browser interface on this computer and open it.

    cropdeck ui                 serves on 127.0.0.1:8737 and opens the browser
    cropdeck ui D:\\Cards       works on that cards folder (remembered for next time)
    cropdeck ui --port 9000     another port
    cropdeck ui --no-browser    serve only
    cropdeck ui --host 100.x.y.z   serve on that one address instead (a private network's)

The port is fixed so a bookmark (and later the installed app window) keeps working; if another
program holds it, the next free one is used and said so. If cropdeck already runs there, a second
`cropdeck ui` only opens the browser. Closing the window (or Ctrl+C) stops it.

Only 127.0.0.1 is bound by default, and never 0.0.0.0 or "::": on WSL with mirrored networking
that would put the UI on the network. --host binds one other address, such as this computer's
address on a private network (a tailnet), to reach the UI from another device of your own. The UI
has no login: everyone who can reach that address can use it.
"""

from __future__ import annotations

import argparse
import ipaddress
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8737
TRIES = 10  # ports tried upwards from the default before giving up
# seconds a stop waits for open connections: a page's live-update stream never ends by itself,
# so without a limit the server would not stop while a browser has it open
STOP_WAIT = 2


def add_arguments(p: argparse.ArgumentParser):
    p.add_argument("folder", nargs="?", default=None, help="cards folder [default: the last one]")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    p.add_argument("--no-browser", action="store_true", help="serve only, do not open a browser")
    p.add_argument("--dev", action="store_true", help="design-check helpers (?theme=dark|light)")
    p.add_argument(
        "--host",
        default=HOST,
        help=f"the one address to serve on (default {HOST}); the UI has no login, so only an "
        "address of a private network of your own",
    )


def check_host(host: str) -> str | None:
    """Why host cannot be served on, or None. One literal address, never "every address"."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return f"--host takes an IP address, not {host!r}"
    if addr.is_unspecified:
        return f"--host {host} would serve on every network; name the one address"
    return None


def authority(host: str, port: int) -> str:
    """host:port as a URL and the Host header write it ([...] around an IPv6 address)."""
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def url(port: int, host: str = HOST) -> str:
    return f"http://{authority(host, port)}/"


def running_cropdeck(port: int, host: str = HOST) -> bool:
    """True if a cropdeck UI already answers on this port."""
    from .app import HEALTH

    try:
        with urllib.request.urlopen(url(port, host) + "health", timeout=1) as r:
            return r.read().decode() == HEALTH
    except OSError:
        return False


def free(port: int, host: str = HOST) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        if sys.platform != "win32":  # as uvicorn binds: a just-closed connection does not count
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def browser_command(target: str, version: str | None = None) -> list[str] | None:
    """The command that opens target in Windows' browser when this runs inside WSL, else None
    (Python's own webbrowser module then knows what to do). Inside WSL it does not: there is no
    Linux browser, and xdg-open is usually missing."""
    if version is None:
        try:
            version = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
        except OSError:
            version = ""
    if "microsoft" not in version.lower():
        return None
    cmd = shutil.which("cmd.exe") or "/mnt/c/Windows/System32/cmd.exe"
    return [cmd, "/c", "start", "", target]


def open_browser(target: str):
    cmd = browser_command(target)
    if cmd is None:
        webbrowser.open(target)
        return
    import subprocess

    subprocess.run(cmd, cwd="/mnt/c", capture_output=True, check=False)


def open_when_ready(port: int, host: str = HOST):
    """Open the browser once the server answers - in the background, the server blocks."""

    def wait():
        for _ in range(100):
            if running_cropdeck(port, host):
                open_browser(url(port, host))
                return
            time.sleep(0.1)

    threading.Thread(target=wait, daemon=True).start()


def run(args) -> int:
    try:
        import uvicorn

        from . import session
        from .app import create_app
    except ImportError:
        print(
            '! The browser interface is not installed:  pip install "cropdeck[ui]"', file=sys.stderr
        )
        return 1

    host = args.host
    refused = check_host(host)
    if refused:
        print(f"! {refused}", file=sys.stderr)
        return 1
    for port in range(args.port, args.port + TRIES):
        if running_cropdeck(port, host):
            print(f"cropdeck already runs at {url(port, host)} - opening it.")
            if not args.no_browser:
                open_browser(url(port, host))
            return 0
        if free(port, host):
            break
        print(f"  port {port} is taken by another program, trying {port + 1}")
    else:
        print(f"! no free port between {args.port} and {args.port + TRIES - 1}", file=sys.stderr)
        return 1

    print(f"cropdeck runs at {url(port, host)}  - close this window or press Ctrl+C to stop it.")
    if host != HOST:
        print("  no login: everyone who can reach this address can use it.")
    if not args.no_browser:
        open_when_ready(port, host)
    work = session.load(Path(args.folder) if args.folder else None)
    app = create_app(port, dev=args.dev, work=work, address=authority(host, port))
    uvicorn.run(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=STOP_WAIT)
    return 0
