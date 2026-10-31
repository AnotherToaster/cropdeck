"""
Reading a posted form. The pages post plain url-encoded forms, which the standard library
reads, so the UI needs no form-parsing package.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import Request

MAX_BODY = 64 * 1024  # a form here holds a path and a few fields, never more


async def read(request: Request) -> dict[str, str]:
    """The posted fields, the first value of each; empty fields are kept as ""."""
    body = await request.body()
    if len(body) > MAX_BODY:
        return {}
    pairs = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: v[0] for k, v in pairs.items()}
