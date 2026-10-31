"""
Running inside WSL (Linux on Windows): the browser is Windows', and so are the paths people
paste - C:\\Users\\... - while this side of the machine sees that drive as /mnt/c/Users/...
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

DRIVE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


@cache
def _version() -> str:
    try:
        return Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def inside(version: str | None = None) -> bool:
    """True when this runs inside WSL (version: /proc/version's text, read if not given)."""
    return "microsoft" in (_version() if version is None else version).lower()


def from_windows(path: str, version: str | None = None) -> str:
    """A Windows path (C:\\Users\\me) as WSL sees it (/mnt/c/Users/me); anything else, and
    everything outside WSL, unchanged."""
    m = DRIVE.match(path.strip())
    if not m or not inside(version):
        return path
    rest = m.group(2).replace("\\", "/").strip("/")
    return f"/mnt/{m.group(1).lower()}" + (f"/{rest}" if rest else "")
