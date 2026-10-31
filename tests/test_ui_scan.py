"""The scan loop in the browser interface (`/`, its events and actions), on synthetic scans.
Skipped where the ui extra is not installed."""

import asyncio
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
    from cropdeck.ui import live, scan_view, session
    from cropdeck.ui.runner import Progress
except (ImportError, RuntimeError):  # the ui extra (or httpx for tests) is not installed
    TestClient = None

HX = {"HX-Request": "true"}


def without_bottom_row(scan):
    out = scan.copy()
    out[round(220 * synth.MM) :, :] = 245
    return out


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class ScanLoop(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.scans = self.home / "scans"
        self.scans.mkdir()
        work = session.Session(self.home, LAYOUTS["s8"])
        self.app = ui_app.create_app(8737, hosts=("testserver",), work=work, watch=False)
        self.client = TestClient(self.app)

    def add_tray(self, seed, backs=True, broken=False, first=1):
        f, b, _ = synth.tray(seed, layout="s8")
        cv2.imwrite(str(self.scans / f"scan_{first:03d}.png"), f)
        if backs:
            back = without_bottom_row(b) if broken else b
            cv2.imwrite(str(self.scans / f"scan_{first + 1:03d}.png"), back)

    def page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        return r.text

    def process(self):
        """Start a run from the page and wait until it is done."""
        r = self.client.post("/process", headers=HX)
        self.assertEqual(r.status_code, 200)
        for _ in range(240):
            if 'aria-label="Working"' not in self.page():
                return
            time.sleep(0.25)
        self.fail("the run did not finish")

    def next_step(self, html):
        """The next-step panels on the page - there must be exactly one."""
        found = re.findall(r'<section id="next-step".*?</section>', html, re.S)
        self.assertEqual(len(found), 1, "exactly one next step")
        self.assertLessEqual(html.count('data-kind="primary"'), 1, "at most one primary button")
        return found[0]

    def test_empty_folder_says_what_to_scan_and_where(self):
        panel = self.next_step(self.page())
        self.assertIn("Scan the fronts of tray 1", panel)
        self.assertIn(str(self.scans), panel)
        self.assertIn("No scans yet", panel)
        self.assertNotIn('action="/process"', panel)  # nothing to process: no live button

    def test_fronts_only_asks_for_the_backs(self):
        self.add_tray(0, backs=False)
        html = self.page()
        panel = self.next_step(html)
        self.assertIn("Flip the cards and scan the backs of tray 1", panel)
        self.assertIn("scan_001.png", panel)
        self.assertIn('data-kind="needs-backs"', html)

    def test_a_run_from_ready_to_done_shows_the_real_cards(self):
        self.add_tray(0)
        panel = self.next_step(self.page())
        self.assertIn("1 tray ready", panel)
        self.assertIn("cards 0001–0008", panel)
        self.process()
        html = self.page()
        panel = self.next_step(html)
        self.assertIn("Tray 1 done", panel)
        self.assertIn("Scan the fronts of tray 2", panel)
        self.assertIn("Next card: 0009.", panel)
        thumbs = re.findall(r'src="(/thumb/[^"]+)"', html)
        self.assertEqual(len(thumbs), 16)  # the latest tray is open: every front and back
        r = self.client.get(thumbs[0])
        self.assertEqual(r.headers["content-type"], "image/jpeg")
        small = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        self.assertLess(small.shape[0], 200)  # a thumbnail, never the full card

    def test_a_refused_tray_stops_with_its_reason_and_can_be_skipped(self):
        self.add_tray(0, broken=True)
        self.add_tray(1, first=3)
        self.process()
        html = self.page()
        panel = self.next_step(html)
        self.assertIn('role="alert"', panel)
        self.assertIn("Tray 1 stopped: 8 fronts but 6 backs", panel)
        self.assertIn('href="/tray/1/stop"', panel)
        self.assertIn("Waiting for tray 1.", html)  # tray 2 waits, visibly
        self.assertFalse(list((self.home / "sorted").glob("card_*")))

        r = self.client.post("/tray/1/skip", headers=HX)
        self.assertEqual(r.status_code, 200)
        html = self.page()
        self.assertIn("1 tray ready", self.next_step(html))
        self.assertIn('data-kind="skipped"', html)
        self.client.post("/tray/1/unskip", headers=HX)
        self.assertIn("Tray 1 stopped", self.next_step(self.page()))

    def test_without_htmx_a_form_post_comes_back_to_the_page(self):
        r = self.client.post("/tray/9/skip", follow_redirects=False)
        self.assertEqual(r.status_code, 404)  # no such tray
        self.add_tray(0, broken=True)
        r = self.client.post("/process", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/"))

    def test_thumbnails_only_for_cards_of_this_folder(self):
        self.add_tray(0)
        for name in ("scan_001.png", "..%2Fscans%2Fscan_001.png", ".cardsplit-state.json"):
            self.assertEqual(self.client.get(f"/thumb/{name}").status_code, 404, name)

    def test_every_event_renders_its_parts(self):
        # while a run goes, an event swaps only the parts it changes; each must render
        from cropdeck.ui.routes import scan as scan_routes

        self.add_tray(0)
        p = Progress([1], 8)
        p.slots = [(1, "card_0001_front.png", "card_0001_rear.png")]
        p.done[1] = 1
        v = scan_view.build(self.home, LAYOUTS["s8"], p)
        self.assertEqual(v.state, scan_view.PROCESSING)
        self.assertEqual([s.state for s in v.slots[:3]], ["done", "working", "pending"])
        html = self.page()  # the page itself: no run is going here
        self.assertIn('sse-connect="/events?page=1"', html)
        names = sorted({n for parts in scan_routes.EVENT_PARTS.values() for n in parts})
        names += [n for n in scan_routes.PAGE_PARTS if n not in names]
        rendered = self.app.state.fragment(scan_routes.PARTIAL, names, v, oob=True)
        for part in ("next-step", "trays", "stats", "run-head", "run-progress", "slots", "halt"):
            self.assertIn(f'id="{part}"', rendered)
        self.assertEqual(rendered.count('hx-swap-oob="true"'), len(names))


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Live(unittest.TestCase):
    def test_an_event_is_one_sse_message_with_every_line_as_data(self):
        self.assertEqual(
            live.sse("card-done", "<a>\n<b>"), "event: card-done\ndata: <a>\ndata: <b>\n\n"
        )

    def test_a_new_scan_is_noticed_and_published(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)

        async def go():
            hub = live.Hub()
            queue = hub.subscribe()
            task = asyncio.create_task(live.watch(lambda: folder, hub, interval=0.05))
            await asyncio.sleep(0.15)
            (folder / "scan_001.png").write_bytes(b"x")
            try:
                return await asyncio.wait_for(queue.get(), 2)
            finally:
                task.cancel()

        self.assertEqual(asyncio.run(go())[0], "scans-changed")


if __name__ == "__main__":
    unittest.main()
