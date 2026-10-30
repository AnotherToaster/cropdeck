"""
Inter (SIL Open Font License) for the generated artwork, fetched when a tool runs and never
committed. One place for the source, so the logo and the demo image always use the same font.
"""

from __future__ import annotations

import urllib.request

URL = "https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/files/inter-latin-{weight}-normal.woff"


def inter(weight: int = 700) -> bytes:
    """The Inter font file (WOFF) in the given weight: 400 regular, 600 semibold, 700 bold."""
    return urllib.request.urlopen(URL.format(weight=weight), timeout=30).read()
