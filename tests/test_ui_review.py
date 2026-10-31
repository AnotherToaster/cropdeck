"""The review in the browser interface (`/review`). Skipped where the ui extra is not installed."""

import html
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cropdeck import manifest, paths  # noqa: E402
from cropdeck.layouts import LAYOUTS  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from cropdeck.ui import app as ui_app
    from cropdeck.ui import review_view, session
except (ImportError, RuntimeError):  # the ui extra (or httpx for tests) is not installed
    TestClient = None


def row(n: int, **fields) -> dict:
    no = f"{n:04d}"
    return {"card": no, "front": f"card_{no}_front.png", "back": f"card_{no}_rear.png", **fields}


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Review(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.out = self.home / paths.SORTED
        self.out.mkdir()
        work = session.Session(self.home, LAYOUTS["s8"], self.home / "ui.json")
        self.c = TestClient(ui_app.create_app(8737, hosts=("testserver",), work=work, watch=False))

    def cards(self, rows):
        manifest.write(self.out, rows)
        img = np.full((88, 63, 3), 128, np.uint8)
        for r in rows:
            for side in ("front", "back"):
                cv2.imwrite(str(self.out / r[side]), img)

    def page(self, query=""):
        return html.unescape(self.c.get(f"/review{query}").text)

    def shown(self, query=""):
        """(number, badge) of every card on the page, in order."""
        found = re.findall(r'id="card-(\d+)".*?data-kind="([\w-]+)"', self.page(query), re.S)
        return [(n, kind) for n, kind in found]

    def test_cards_that_need_a_look_come_first_and_are_counted(self):
        self.cards(
            [
                row(1, accepted="yes", name="Pikachu"),
                row(2),
                row(3, confidence="-"),  # recognition read nothing
                row(4, name="Charmander", confidence="0.84"),  # a weak match
                row(5, name="Bulbasaur", confidence="0.97"),
            ]
        )
        self.assertEqual(
            self.shown(),
            [("0003", "unread"), ("0004", "check"), ("0002", "filled"), ("0005", "filled"),
             ("0001", "accepted")],
        )  # fmt: skip
        page = self.page()
        self.assertIn("5 cards · 2 need a look · 3 filled in", re.sub(r"<[^>]+>", "", page))
        self.assertIn('aria-label="2 need a look"', page)  # the nav pill
        self.assertIn("Couldn't read the text.", page)
        self.assertEqual(
            [n for n, _ in self.shown("?show=order")], ["0001", "0002", "0003", "0004", "0005"]
        )
        self.assertEqual(self.shown("?show=accepted"), [("0001", "accepted")])

    def test_a_field_is_saved_as_it_is_left_and_typing_settles_a_check(self):
        self.cards([row(4, name="Charmander", confidence="0.84")])
        r = self.c.post("/review/0004/field", data={"name": "Glumanda"})
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="badge-0004"', r.text)
        self.assertIn('data-kind="filled"', r.text)
        self.assertIn('id="review-pill" hx-swap-oob="true"></span>', r.text)  # none left
        saved = manifest.read(self.out)[0]
        self.assertEqual((saved["name"], saved["typed"]), ("Glumanda", "name"))

    def test_an_edit_takes_one_known_field_of_a_known_card(self):
        self.cards([row(1)])
        self.assertEqual(
            self.c.post("/review/0001/field", data={"name": "a", "set": "b"}).status_code, 422
        )
        self.assertEqual(
            self.c.post("/review/0001/field", data={"front": "x.png"}).status_code, 422
        )
        self.assertEqual(self.c.post("/review/0099/field", data={"name": "a"}).status_code, 404)
        self.assertEqual(manifest.read(self.out)[0]["front"], "card_0001_front.png")

    def test_accept_saves_every_field_and_marks_the_card(self):
        self.cards([row(1), row(2)])
        r = self.c.post("/review/0001/accept", data={"name": "Mew", "number": "151", "set": ""})
        self.assertIn('id="card-0001"', r.text)
        self.assertIn("Accepted", r.text)
        saved = manifest.read(self.out)[0]
        self.assertEqual((saved["name"], saved["number"], saved["accepted"]), ("Mew", "151", "yes"))
        self.assertEqual(self.shown("?show=accepted"), [("0001", "accepted")])

    def test_the_true_size_view_gets_the_full_cards_and_only_this_folders(self):
        self.cards([row(1)])
        page = self.page()
        front = re.search(r'data-front="([^"]+)"', page).group(1)
        self.assertEqual(front, "/card/card_0001_front.png")
        self.assertEqual(self.c.get(front).headers["content-type"], "image/png")
        self.assertEqual(self.c.get("/card/other.png").status_code, 404)
        thumb = re.search(r'<img src="(/thumb/[^"]+)"', page).group(1)
        self.assertTrue(thumb.endswith("?size=large"))
        self.assertEqual(self.c.get(thumb).status_code, 200)

    def test_a_page_holds_forty(self):
        self.cards([row(n) for n in range(1, 42)])
        self.assertEqual(len(self.shown()), review_view.PER_PAGE)
        self.assertEqual([n for n, _ in self.shown("?page=2")], ["0041"])
        self.assertIn("Page 1 of 2", self.page())

    def test_without_cards_it_says_so(self):
        self.assertIn("No cards yet.", self.page())


if __name__ == "__main__":
    unittest.main()
