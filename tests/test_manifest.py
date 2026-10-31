"""cards.csv: edits from the review, what recognition may overwrite, writers that overlap."""

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cropdeck import manifest  # noqa: E402


def row(n: int, **fields) -> dict:
    no = f"{n:04d}"
    return {"card": no, "front": f"card_{no}_front.png", "back": f"card_{no}_rear.png", **fields}


class Manifest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_an_edit_marks_only_the_fields_that_changed_as_typed(self):
        manifest.write(self.out, [row(1, name="Pikachu"), row(2)])
        got = manifest.update(self.out, "0001", {"name": "Pikachu", "number": "25/102"})
        self.assertEqual(got["typed"], "number")
        self.assertEqual(manifest.read(self.out)[0]["number"], "25/102")
        self.assertEqual(manifest.read(self.out)[1]["card"], "0002")  # the other row stays
        self.assertIsNone(manifest.update(self.out, "0009", {"name": "x"}))

    def test_recognition_never_writes_over_what_was_typed(self):
        typed = {**row(1, name="Glurak", number="4/102"), "typed": "name"}
        found = {"card": "0001", "name": "Charizard", "number": "4/102", "confidence": "0.84"}
        merged = manifest.recognised(typed, found)
        self.assertEqual((merged["name"], merged["confidence"]), ("Glurak", "0.84"))

    def test_a_run_appending_and_a_review_editing_lose_nothing_of_each_other(self):
        manifest.write(self.out, [row(1)])

        def run():
            for n in range(2, 42):
                manifest.append(self.out, [row(n)])

        worker = threading.Thread(target=run)
        worker.start()
        for i in range(40):
            manifest.update(self.out, "0001", {"name": f"edit {i}"})
        worker.join()
        rows = manifest.read(self.out)
        self.assertEqual(len(rows), 41)
        self.assertEqual(rows[0]["name"], "edit 39")


if __name__ == "__main__":
    unittest.main()
