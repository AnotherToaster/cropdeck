"""The guard stops in the browser interface (`/tray/{n}/stop` and its fixes), on synthetic scans.
Skipped where the ui extra is not installed."""

import html
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import synth  # noqa: E402

from cropdeck.layouts import LAYOUTS  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from cropdeck.ui import app as ui_app
    from cropdeck.ui import session
except (ImportError, RuntimeError):  # the ui extra (or httpx for tests) is not installed
    TestClient = None

MM = synth.MM


def moved_card_five(backs):
    """The backs scan with card 5 (s8: third row, left) pushed down into the empty fourth row."""
    out = synth.blank(backs, 220)
    y0, y1, x0, x1 = (round(v * MM) for v in (150, 221, 8, 104))
    shift = round(71 * MM)
    out[y0 + shift : y1 + shift, x0:x1] = out[y0:y1, x0:x1]
    out[y0:y1, x0:x1] = 245
    return out


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class GuardStop(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.scans = self.home / "scans"
        self.scans.mkdir()
        work = session.Session(self.home, LAYOUTS["s8"])
        self.client = TestClient(
            ui_app.create_app(8737, hosts=("testserver",), work=work, watch=False)
        )

    def scan(self, name, img):
        cv2.imwrite(str(self.scans / name), img)

    def settle(self):
        """Wait until no run is going."""
        for _ in range(240):
            if 'aria-label="Working"' not in self.client.get("/").text:
                return
            time.sleep(0.25)
        self.fail("the run did not finish")

    def run_until_stopped(self):
        self.client.post("/process", follow_redirects=False)
        self.settle()

    def stop_page(self, n=1):
        r = self.client.get(f"/tray/{n}/stop")
        self.assertEqual(r.status_code, 200, r.text[:500])
        return html.unescape(r.text)

    def fixes(self, n=1):
        """The fixes the stop page offers, in order."""
        return re.findall(rf'action="/tray/{n}/fix/(\w+)"', self.stop_page(n))

    def fix(self, action, n=1):
        r = self.client.post(f"/tray/{n}/fix/{action}", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/"))
        self.settle()

    def cards(self):
        return sorted(p.name for p in (self.home / "sorted").glob("card_*_front.png"))

    def test_count_shows_both_scans_and_the_missing_spots_then_writes_the_pairs(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.scan("scan_001.png", f)
        self.scan("scan_002.png", synth.blank(b, 220))
        f2, b2, _ = synth.tray(1, layout="s8")
        self.scan("scan_003.png", f2)
        self.scan("scan_004.png", b2)
        self.run_until_stopped()
        page = self.stop_page()
        self.assertIn("Tray 1 stopped: 8 fronts but 6 backs", page)
        self.assertIn("Missing on the backs scan: 7 and 8.", page)
        self.assertEqual(page.count('data-kind="missing"'), 2)
        self.assertEqual(page.count('data-kind="matched"'), 14)  # all 8 fronts, the 6 backs
        self.assertEqual(self.fixes(), ["rescan", "pairs_only", "skip"])
        self.assertIn("Process with 6 pairs", page)
        self.assertIn("Tray 2", page)  # waits, visibly
        for side in ("front", "back"):
            r = self.client.get(f"/tray/1/scan/{side}.jpg")
            self.assertEqual(r.headers["content-type"], "image/jpeg")
            small = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            self.assertLessEqual(max(small.shape[:2]), 900)

        self.fix("pairs_only")  # writes the six, then tray 2 runs on
        self.assertEqual(len(self.cards()), 14)
        self.assertEqual(self.client.get("/tray/1/stop", follow_redirects=False).status_code, 303)
        self.assertTrue((self.scans / "scan_002.png").exists())

    def test_a_rescan_waits_for_the_next_scan(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.scan("scan_001.png", f)
        self.scan("scan_002.png", synth.blank(b, 220))
        self.run_until_stopped()
        self.fix("rescan")
        self.assertIn("Scan the backs of tray 1 again", self.client.get("/").text)
        self.scan("scan_003.png", b)
        self.client.post("/process", follow_redirects=False)
        self.settle()
        self.assertEqual(len(self.cards()), 8)

    def test_swapped_scans_offer_the_swap(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.scan("scan_001.png", f)
        self.scan("scan_002.png", b)
        f2, b2, _ = synth.tray(1, layout="s8")
        self.scan("scan_003.png", b2)
        self.scan("scan_004.png", f2)
        self.run_until_stopped()
        page = self.stop_page(2)
        self.assertIn("fronts and backs look swapped", page)
        self.assertEqual(self.fixes(2), ["swap", "keep", "skip"])
        self.assertIn("scan_004.png is read as fronts, scan_003.png as backs.", page)
        self.fix("swap", 2)
        self.assertEqual(len(self.cards()), 16)

    def test_another_back_design_offers_to_learn_it(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.scan("scan_001.png", f)
        self.scan("scan_002.png", b)
        f2, b2, _ = synth.tray(1, layout="s8", back=synth.other_back())
        self.scan("scan_003.png", f2)
        self.scan("scan_004.png", b2)
        self.run_until_stopped()
        page = self.stop_page(2)
        self.assertIn("the second scan isn't backs", page)
        self.assertEqual(self.fixes(2), ["forgot", "new_back", "skip"])
        self.fix("new_back", 2)
        self.assertEqual(len(self.cards()), 16)

    def test_a_moved_card_is_shown_where_it_lies_and_where_it_was(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.scan("scan_001.png", synth.blank(f, 220))
        self.scan("scan_002.png", moved_card_five(b))
        self.run_until_stopped()
        page = self.stop_page()
        self.assertIn("Tray 1 stopped: a card moved", page)
        self.assertIn("Moved between the scans: 5.", page)
        self.assertEqual(page.count('data-kind="suspicious"'), 2)  # its front, and its back
        self.assertEqual(page.count('data-kind="missing"'), 1)  # its spot on the backs scan
        self.assertEqual(self.cards(), [])

    def test_only_known_fixes_and_existing_trays(self):
        self.assertEqual(self.client.post("/tray/1/fix/delete").status_code, 404)
        self.assertEqual(self.client.post("/tray/7/fix/skip").status_code, 404)
        self.assertEqual(self.client.get("/tray/1/scan/left.jpg").status_code, 404)


if __name__ == "__main__":
    unittest.main()
