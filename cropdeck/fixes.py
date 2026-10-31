"""
The fixes for a tray that was refused. Each one is a choice recorded in the state file
(state["trays"][n]); no scan is ever renamed, moved or deleted. The caller saves the state.

  rescan      the next new scan becomes the tray's backs; the old backs scan is marked unused
              (keep_old: it stays in the sequence instead - "I forgot to scan the backs", so it
              was really the next tray's fronts)
  pairs_only  write the slots that have both sides, leave out the rest
  new_back    the backs are another back design: learn it for the folder and pair
  swap        read the second scan as the fronts and the first as the backs
  keep        take the tray as scanned, without the backs check
  skip        pass the tray over for now; unskip brings it back as it was
"""

from __future__ import annotations

from pathlib import Path

from .trays import Tray, choices


def _fresh(state: dict, n: int) -> dict:
    """The tray's choices with the old stop cleared: the next run checks it again."""
    c = choices(state, n)
    c.pop("stop", None)
    return c


def rescan(state: dict, tray: Tray, files: list[Path], keep_old: bool = False) -> None:
    c = _fresh(state, tray.n)
    if tray.back is not None and not keep_old:
        c.setdefault("unused", []).append(tray.back.name)
    c.pop("back", None)
    c["await_after"] = max((f.name for f in files), default="")


def pairs_only(state: dict, n: int) -> None:
    _fresh(state, n)["pairs_only"] = True


def new_back(state: dict, n: int) -> None:
    _fresh(state, n)["new_back"] = True


def swap(state: dict, n: int) -> None:
    _fresh(state, n)["swap"] = True


def keep(state: dict, n: int) -> None:
    _fresh(state, n)["keep"] = True


def skip(state: dict, n: int) -> None:
    choices(state, n)["skip"] = True  # the stop stays: unskip shows why it was refused


def unskip(state: dict, n: int) -> None:
    choices(state, n).pop("skip", None)
