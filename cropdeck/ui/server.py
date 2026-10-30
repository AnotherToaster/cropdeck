"""
cropdeck ui - start the browser interface on this computer and open it.

    cropdeck ui                 serves on 127.0.0.1:8737 and opens the browser
    cropdeck ui --port 9000     another port
    cropdeck ui --no-browser    serve only

The port is fixed so a bookmark (and later the installed app window) keeps working; if another
program holds it, the next free one is used and said so. If cropdeck already runs there, a second
`cropdeck ui` only opens the browser. Closing the window (or Ctrl+C) stops it.

Only 127.0.0.1 is bound, never 0.0.0.0: on WSL with mirrored networking that would put the UI on
the network.
"""

from __future__ import annotations

import argparse
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


def add_arguments(p: argparse.ArgumentParser):
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    p.add_argument("--no-browser", action="store_true", help="serve only, do not open a browser")
    p.add_argument("--dev", action="store_true", help="design-check helpers (?theme=dark|light)")


def url(port: int) -> str:
    return f"http://{HOST}:{port}/"


def running_cropdeck(port: int) -> bool:
    """True if a cropdeck UI already answers on this port."""
    from .app import HEALTH

    try:
        with urllib.request.urlopen(url(port) + "health", timeout=1) as r:
            return r.read().decode() == HEALTH
    except OSError:
        return False


def free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
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


def open_when_ready(port: int):
    """Open the browser once the server answers - in the background, the server blocks."""

    def wait():
        for _ in range(100):
            if running_cropdeck(port):
                open_browser(url(port))
                return
            time.sleep(0.1)

    threading.Thread(target=wait, daemon=True).start()


def run(args) -> int:
    try:
        import uvicorn

        from .app import create_app
    except ImportError:
        print(
            '! The browser interface is not installed:  pip install "cropdeck[ui]"', file=sys.stderr
        )
        return 1

    for port in range(args.port, args.port + TRIES):
        if running_cropdeck(port):
            print(f"cropdeck already runs at {url(port)} - opening it.")
            if not args.no_browser:
                open_browser(url(port))
            return 0
        if free(port):
            break
        print(f"  port {port} is taken by another program, trying {port + 1}")
    else:
        print(f"! no free port between {args.port} and {args.port + TRIES - 1}", file=sys.stderr)
        return 1

    print(f"cropdeck runs at {url(port)}  - close this window or press Ctrl+C to stop it.")
    if not args.no_browser:
        open_when_ready(port)
    uvicorn.run(create_app(port, dev=args.dev), host=HOST, port=port, log_level="warning")
    return 0
