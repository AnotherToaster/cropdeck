"""
Which cards folder the UI works on, and how the cards lie on its glass.

The folder comes from `cropdeck ui FOLDER`, or else is the one used last time - remembered in the
user's own config folder, never in the cards folder or the repository. The layout is the one
chosen for that folder (kept in its state file by setup) or the default.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import paths, state
from ..layouts import DEFAULT, LAYOUTS, Layout


def config_file() -> Path:
    """Where the UI remembers the last folder: %APPDATA% on Windows, ~/.config elsewhere."""
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "cropdeck" / "ui.json"


@dataclass
class Session:
    folder: Path | None
    layout: Layout


def layout_of(folder: Path) -> Layout:
    chosen = state.load_state(folder / paths.SORTED).get("layout")
    return LAYOUTS.get(chosen, LAYOUTS[DEFAULT])


def load(folder: Path | None, config: Path | None = None) -> Session:
    """The session for `cropdeck ui [FOLDER]`: a folder given is remembered for next time."""
    config = config or config_file()
    if folder is not None:
        folder = folder.expanduser().resolve()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"folder": str(folder)}), encoding="utf-8")
    elif config.exists():
        try:
            last = json.loads(config.read_text(encoding="utf-8")).get("folder")
        except (OSError, ValueError):
            last = None
        folder = Path(last) if last and Path(last).is_dir() else None
    return Session(folder, layout_of(folder) if folder else LAYOUTS[DEFAULT])
