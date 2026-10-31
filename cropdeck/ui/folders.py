"""
Picking the cards folder in setup: the in-page folder browser and the checks before a folder is
used. The server runs on the user's own computer, so the page can list its folders - only folder
names, never files, and nothing hidden. Inside WSL a pasted Windows path (C:\\Users\\...) is
taken as the same folder under /mnt/c.
"""

from __future__ import annotations

import os
import string
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from . import wsl

# characters Windows refuses in a folder name; "/" and "\\" also split a path everywhere
BAD_NAME_CHARS = set('<>:"/\\|?*')


@dataclass
class Listing:
    path: Path | None  # None: the top, where the drives (or "/") are listed
    parent: Path | None
    folders: list[Path] = field(default_factory=list)
    error: str | None = None  # a text key


def roots() -> list[Path]:
    """Where browsing starts above everything: the drives on Windows, "/" elsewhere."""
    if sys.platform == "win32":
        return [Path(f"{d}:\\") for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    return [Path("/")]


def _visible(name: str) -> bool:
    return not name.startswith(".") and not name.startswith("$")


def _folders(here: Path) -> list[Path]:
    """The visible folders in here. An entry that cannot be looked at (pagefile.sys and
    "System Volume Information" on a Windows drive) is left out, not the whole folder."""
    found = []
    with os.scandir(here) as entries:
        for e in entries:
            if not _visible(e.name):
                continue
            try:
                if e.is_dir():
                    found.append(Path(e.path))
            except OSError:
                continue
    return sorted(found, key=lambda p: p.name.lower())


def listing(path: str | None) -> Listing:
    """The folders inside path; no path (or one that is not a folder) lists the roots."""
    if not path:
        return Listing(None, None, roots())
    here = Path(wsl.from_windows(path)).expanduser()
    if not here.is_absolute() or not here.is_dir():
        return Listing(None, None, roots(), "setup.error.not_found")
    here = here.resolve()
    up = here.parent if here.parent != here else None
    try:
        found = _folders(here)
    except OSError:
        return Listing(here, up, [], "setup.error.unreadable")
    return Listing(here, up, found)


def make(parent: str, name: str) -> tuple[Path | None, str | None]:
    """A new folder called name inside parent: (the folder, None) or (None, a text key)."""
    name = name.strip()
    if not name or name in (".", "..") or BAD_NAME_CHARS & set(name):
        return None, "setup.error.bad_name"
    base = Path(wsl.from_windows(parent)).expanduser()
    if not base.is_absolute() or not base.is_dir():
        return None, "setup.error.not_found"
    new = base / name
    try:
        new.mkdir()
    except FileExistsError:
        return None, "setup.error.exists"
    except OSError:
        return None, "setup.error.not_writable"
    return new.resolve(), None


def prepare(path: str) -> tuple[Path | None, str | None]:
    """Make path ready as a cards folder: scans/ and sorted/ inside it, and proof it can be
    written to. (the folder, None) or (None, a text key). The folder itself may be new, as long
    as the folder it goes into exists."""
    if not path.strip():
        return None, "setup.error.empty"
    folder = Path(wsl.from_windows(path)).expanduser()
    if not folder.is_absolute():
        return None, "setup.error.not_absolute"
    if not folder.is_dir() and not folder.parent.is_dir():
        return None, "setup.error.no_parent"
    try:
        for sub in ("", paths.SCANS, paths.SORTED):
            (folder / sub).mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=folder / paths.SORTED):
            pass
    except OSError:
        return None, "setup.error.not_writable"
    return folder.resolve(), None
