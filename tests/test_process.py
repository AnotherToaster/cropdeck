"""The tray-by-tray core (cropdeck/process.py, trays.py, fixes.py) on synthetic scans.

These call the core directly rather than through the command line: what is checked is the order
of events, what reaches the state file and that a refused tray writes nothing.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import synth  # noqa: E402

from cropdeck import fixes, manifest, process, split, trays  # noqa: E402
from cropdeck.imageio import IMAGE_EXTS  # noqa: E402
from cropdeck.state import load_state, save_state  # noqa: E402

OPTS = split.options(dpi=synth.DPI, expect=8, no_sheet=True)


def without_bottom_row(scan):
    """The scan with the s8 layout's bottom row (cards 7 and 8) taken off the glass."""
    out = scan.copy()
    out[round(220 * synth.MM) :, :] = 245
    return out


def other_back():
    """A second back design: plain dark red with a pale stripe, unlike synth's blue one."""
    img = np.full((synth.CARD_H, synth.CARD_W, 3), (40, 40, 160), np.uint8)
    top, bottom = synth.CARD_H // 3, synth.CARD_H // 2
    cv2.rectangle(img, (0, top), (synth.CARD_W, bottom), (220, 220, 220), -1)
    return img


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scans, self.out = self.tmp / "scans", self.tmp / "sorted"
        self.scans.mkdir()
        self.out.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def add(self, name, img):
        cv2.imwrite(str(self.scans / name), img)

    def files(self):
        return sorted(f for f in self.scans.iterdir() if f.suffix.lower() in IMAGE_EXTS)

    def folder(self, state):
        return trays.build(self.files(), state, manifest.read(self.out))

    def run_all(self, halt=lambda: False):
        """One run over everything runnable; returns (events, state as saved)."""
        state = load_state(self.out)
        events = list(
            process.run(trays.runnable(self.folder(state)), OPTS, state, self.out, halt=halt)
        )
        return events, load_state(self.out)

    def fix(self, action, n, **kw):
        state = load_state(self.out)
        tray = self.folder(state)[n - 1]
        if action is fixes.rescan:
            action(state, tray, self.files(), **kw)
        else:
            action(state, n)
        save_state(self.out, state)

    def assert_paired(self):
        for fp in sorted(self.out.glob("card_*_front.png")):
            front, back = cv2.imread(str(fp)), cv2.imread(str(fp).replace("_front", "_rear"))
            self.assertTrue(
                all(
                    abs(a - b) <= 40
                    for a, b in zip(synth.mark_colour(front), synth.mark_colour(back), strict=True)
                ),
                fp.name,
            )

    def test_events_of_a_clean_run_in_order(self):
        for i, seed in enumerate((0, 1)):
            f, b, _ = synth.tray(seed, layout="s8")
            self.add(f"scan_{2 * i + 1:03d}.png", f)
            self.add(f"scan_{2 * i + 2:03d}.png", b)
        events, state = self.run_all()
        kinds = [type(e).__name__ for e in events if not isinstance(e, process.Note)]
        self.assertEqual(
            kinds,
            ["TrayStart"]
            + ["CardDone"] * 8
            + ["TrayDone", "TrayStart"]
            + ["CardDone"] * 8
            + ["TrayDone", "RunDone"],
        )
        self.assertEqual([e.card for e in events if isinstance(e, process.CardDone)][-1], 16)
        self.assertEqual((events[-1].cards, events[-1].trays, events[-1].halted), (16, 2, False))
        self.assertEqual([t.cards for t in self.folder(state)], [(1, 8), (9, 16)])

    def test_stop_after_this_tray(self):
        for i, seed in enumerate((0, 1)):
            f, b, _ = synth.tray(seed, layout="s8")
            self.add(f"scan_{2 * i + 1:03d}.png", f)
            self.add(f"scan_{2 * i + 2:03d}.png", b)
        events, state = self.run_all(halt=lambda: True)
        self.assertTrue(events[-1].halted)
        self.assertEqual([t.status for t in self.folder(state)], [trays.DONE, trays.READY])

    def test_a_count_mismatch_stops_and_later_trays_wait(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.add("scan_001.png", f)
        self.add("scan_002.png", without_bottom_row(b))
        f2, b2, _ = synth.tray(1, layout="s8")
        self.add("scan_003.png", f2)
        self.add("scan_004.png", b2)
        events, state = self.run_all()
        stop = next(e for e in events if isinstance(e, process.TrayStopped))
        self.assertEqual(stop.kind, process.COUNT)
        self.assertEqual(stop.detail["missing"], [7, 8])
        self.assertEqual((stop.detail["front_count"], stop.detail["back_count"]), (8, 6))
        self.assertEqual(sum(isinstance(e, process.TrayStart) for e in events), 1)  # tray 2 waits
        self.assertEqual(list(self.out.glob("card_*")), [])
        folder = self.folder(state)
        self.assertEqual([t.status for t in folder], [trays.STOPPED, trays.READY])
        self.assertEqual(trays.runnable(folder), [])

        # the fix: write the six that have both sides; tray 2 then follows on from card 7
        self.fix(fixes.pairs_only, 1)
        events, state = self.run_all()
        self.assertEqual([t.cards for t in self.folder(state)], [(1, 6), (7, 14)])
        self.assert_paired()

    def test_a_rescan_becomes_the_trays_backs_and_the_order_holds(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.add("scan_001.png", f)
        self.add("scan_002.png", without_bottom_row(b))
        f2, b2, _ = synth.tray(1, layout="s8")
        self.add("scan_003.png", f2)
        self.add("scan_004.png", b2)
        self.run_all()
        self.fix(fixes.rescan, 1)
        state = load_state(self.out)
        self.assertEqual(self.folder(state)[0].status, trays.NEEDS_BACKS)

        self.add("scan_005.png", b)  # the backs, scanned again with all eight
        folder = self.folder(load_state(self.out))
        self.assertEqual(
            [(t.front.name, t.back.name) for t in folder],
            [("scan_001.png", "scan_005.png"), ("scan_003.png", "scan_004.png")],
        )
        events, state = self.run_all()
        self.assertEqual([t.cards for t in self.folder(state)], [(1, 8), (9, 16)])
        self.assertEqual(state["trays"]["1"]["back"], "scan_005.png")  # pinned once used
        self.assertIn("scan_002.png", state["trays"]["1"]["unused"])
        self.assertTrue((self.scans / "scan_002.png").exists())  # never deleted
        self.assert_paired()

    def test_swapped_scans_are_refused_then_read_the_other_way_round(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.add("scan_001.png", f)
        self.add("scan_002.png", b)
        f2, b2, _ = synth.tray(1, layout="s8")
        self.add("scan_003.png", b2)  # backs first: the tray went in face down
        self.add("scan_004.png", f2)
        events, _ = self.run_all()
        self.assertEqual(events[-2].kind, process.SWAPPED)
        self.fix(fixes.swap, 2)
        events, state = self.run_all()
        self.assertEqual([t.status for t in self.folder(state)], [trays.DONE, trays.DONE])
        self.assert_paired()
        self.assertTrue((self.out / "card_0016_front.png").exists())

    def test_a_second_back_design_is_learnt_once(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.add("scan_001.png", f)
        self.add("scan_002.png", b)
        for i, seed in enumerate((1, 2)):
            f2, b2, _ = synth.tray(seed, layout="s8", back=other_back())
            self.add(f"scan_{2 * i + 3:03d}.png", f2)
            self.add(f"scan_{2 * i + 4:03d}.png", b2)
        events, _ = self.run_all()
        self.assertEqual(events[-2].kind, process.NOTBACKS)
        self.fix(fixes.new_back, 2)
        events, state = self.run_all()  # tray 3 has the new design too and passes unasked
        self.assertEqual([t.status for t in self.folder(state)], [trays.DONE] * 3)
        self.assertEqual(len(state["back_refs"]), 2)
        self.assert_paired()

    def test_a_skipped_tray_is_passed_over(self):
        f, b, _ = synth.tray(0, layout="s8")
        self.add("scan_001.png", f)
        self.add("scan_002.png", without_bottom_row(b))
        f2, b2, _ = synth.tray(1, layout="s8")
        self.add("scan_003.png", f2)
        self.add("scan_004.png", b2)
        self.run_all()
        self.fix(fixes.skip, 1)
        events, state = self.run_all()
        self.assertEqual([t.status for t in self.folder(state)], [trays.SKIPPED, trays.DONE])
        self.assertEqual(self.folder(state)[1].cards, (1, 8))


if __name__ == "__main__":
    unittest.main()
