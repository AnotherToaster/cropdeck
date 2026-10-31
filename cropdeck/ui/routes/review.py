"""
The review (`/review`): every card with its fields, the ones that need a look first. A field is
saved the moment it is left (htmx posts it alone), Accept saves the card's fields and marks it
accepted. Both write cards.csv through manifest.update, which keeps what the user typed safe from
recognition later. Edits are allowed while a run goes: the run and the review share one lock.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import manifest, paths
from .. import forms, review_view

PARTIAL = "partials/review.html"


def register(app, render, fragment, work):
    def need_folder():
        if work.folder is None:
            raise HTTPException(409, "No cards folder is set up yet.")

    def save(card: str, values: dict[str, str]) -> review_view.Card:
        need_folder()
        row = manifest.update(work.folder / paths.SORTED, card, values)
        if row is None:
            raise HTTPException(404, f"There is no card {card}.")
        return review_view.card_of(row)

    def counts_parts() -> str:
        counts = review_view.counts(review_view.all_cards(work.folder))
        return fragment(PARTIAL, ("counts", "nav_pill"), counts, oob=True)

    @app.get("/review")
    def review(request: Request, show: str = "look", page: int = 1):
        if work.folder is None:
            return RedirectResponse("/setup", status_code=303)
        v = review_view.build(work.folder, show, page)
        return render(request, "pages/review.html", current="review", v=v)

    @app.post("/review/{card}/field", response_class=HTMLResponse)
    async def field(card: str, request: Request):
        """One field, as it was left. Answers with the card's badge and the counts."""
        form = await forms.read(request)
        values = {k: v.strip() for k, v in form.items() if k in review_view.FIELDS}
        if len(values) != 1:
            raise HTTPException(422, "Send one field.")
        c = save(card, values)
        return fragment(PARTIAL, ("badge_of",), c, oob=True) + counts_parts()

    @app.post("/review/{card}/accept", response_class=HTMLResponse)
    async def accept(card: str, request: Request):
        """The card's fields as they stand, and accepted. Answers with the card itself."""
        form = await forms.read(request)
        values = {k: form[k].strip() for k in review_view.FIELDS if k in form}
        c = save(card, {**values, "accepted": "yes"})
        return fragment(PARTIAL, ("card",), c) + counts_parts()
