"""
Every string the UI shows goes through t(): the wording lives in data/locales/ui/<code>.json,
never in a template, so German (or any language) can follow by adding one file.

The UI's strings are kept apart from the tracker's (data/locales/<code>.json): the tracker's
languages are complete today, the UI's German is not written yet.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / "data" / "locales" / "ui"
DEFAULT = "en"


@cache
def strings(lang: str) -> dict:
    path = LOCALES / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def t(key: str, lang: str = DEFAULT, **values) -> str:
    """The text for a dotted key ("app.name"), in lang, falling back to English.

    A missing key raises KeyError: a string nobody wrote must fail loudly in the tests, not show
    up on screen as a key.
    """
    for source in (strings(lang), strings(DEFAULT)):
        node = source
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, str):
            return node.format(**values) if values else node
    raise KeyError(f"no UI text for {key!r}")
