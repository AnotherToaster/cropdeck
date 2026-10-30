"""
Where cropdeck looks by default: one folder that holds scans/ and receives sorted/ and the
tracker workbook. It is $CROPDECK_HOME when set, otherwise the current directory.

Every default path is derived here, so the subcommands can never disagree about where
the scans are.
"""

from __future__ import annotations

import os
from pathlib import Path

SCANS = "scans"
SORTED = "sorted"
TRACKER = "Karten-Tracker.xlsx"


def home() -> Path:
    return Path(os.environ.get("CROPDECK_HOME", ".")).expanduser()
