"""
Resume state: which scans have already been cut, and what card number we are up to.
Kept in the output folder so you can leave finished scans sitting in the scans
folder and just keep adding to them.
"""

from __future__ import annotations

import json
from pathlib import Path

# The name predates the package; it stays so existing output folders keep resuming.
STATE_FILE = ".cardsplit-state.json"


def load_state(out_dir: Path) -> dict:
    f = out_dir / STATE_FILE
    if f.exists():
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
            st.setdefault("next", 1)
            st.setdefault("done", {})
            return st
        except Exception:
            pass
    return {"next": 1, "done": {}}


def save_state(out_dir: Path, state: dict):
    try:
        (out_dir / STATE_FILE).write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass


def scan_key(path: Path) -> str:
    """Identify a scan by name and size - enough to spot 'same file as last time'."""
    try:
        return f"{path.name}|{path.stat().st_size}"
    except OSError:
        return path.name
