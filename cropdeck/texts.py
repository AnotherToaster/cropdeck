"""
Everything a person reads in the tracker comes from data files, not from the code:

  data/locales/<code>.json   one file per language - sheet names, columns, statuses, labels
  data/currencies.json       one entry per currency - the platforms offered in its dropdown

Adding a language or a currency is adding a file or an entry; tests check that every language
has exactly the keys English has.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "EUR"


def languages() -> list[str]:
    """Codes of every language there is a file for, e.g. ['de', 'en']."""
    return sorted(p.stem for p in (DATA / "locales").glob("*.json"))


@cache
def language(code: str) -> dict:
    return json.loads((DATA / "locales" / f"{code}.json").read_text(encoding="utf-8"))


@cache
def currencies() -> dict[str, dict]:
    return json.loads((DATA / "currencies.json").read_text(encoding="utf-8"))
