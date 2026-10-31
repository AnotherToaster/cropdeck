"""Setup in the browser interface (`/setup`): the cards folder, its layout, the folder browser.
Skipped where the ui extra is not installed."""

import html as html_lib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cropdeck import paths  # noqa: E402
from cropdeck.state import load_state  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from cropdeck.ui import app as ui_app
    from cropdeck.ui import runner, session
except (ImportError, RuntimeError):  # the ui extra (or httpx for tests) is not installed
    TestClient = None


def alert(html: str) -> list[str]:
    return [html_lib.unescape(m) for m in re.findall(r'role="alert">([^<]*)<', html)]


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Setup(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.config = self.home / "config" / "ui.json"
        self.work = session.load(None, self.config)
        app = ui_app.create_app(8737, hosts=("testserver",), work=self.work, watch=False)
        self.c = TestClient(app)

    def choose(self, folder, layout="s8"):
        return self.c.post(
            "/setup", data={"folder": str(folder), "layout": layout}, follow_redirects=False
        )

    def test_first_start_shows_only_the_logo_and_every_layout(self):
        html = self.c.get("/setup").text
        self.assertIn('class="brand"', html)
        self.assertNotIn('<nav class="nav"', html)
        self.assertEqual(re.findall(r'name="layout" value="(\w+)"', html), ["s8", "s6", "u6", "u9"])
        self.assertIn('value="s8" checked', html)  # the default
        self.assertEqual(html.count('type="checkbox"'), 4)

    def test_a_chosen_folder_is_set_up_remembered_and_keeps_its_layout(self):
        folder = self.home / "Cards"  # new: its parent exists, so it is created
        r = self.choose(folder, "u9")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/"))
        self.assertTrue((folder / paths.SCANS).is_dir())
        self.assertEqual(load_state(folder / paths.SORTED)["layout"], "u9")
        self.assertEqual(session.load(None, self.config).folder, folder)
        html = self.c.get("/").text
        self.assertIn("9 upright", html)  # the header's layout chip
        self.assertIn(str(folder / paths.SCANS), html)  # where to save scans
        again = self.c.get("/setup").text  # later: the full header, the folder filled in
        self.assertIn('<nav class="nav"', again)
        self.assertIn(f'value="{folder}"', again)
        self.assertIn('value="u9" checked', again)

    def test_a_folder_that_cannot_be_used_is_refused_and_kept_in_the_field(self):
        for typed, says in (
            ("", "Enter a folder."),
            ("cards/here", "Enter the full path, from the drive or /."),
            (str(self.home / "no" / "such"), "The folder it goes in doesn't exist."),
        ):
            r = self.choose(typed)
            self.assertEqual(r.status_code, 422, typed)
            self.assertEqual(alert(r.text), [says])
            self.assertIn(f'value="{typed}"', r.text)
        self.assertIsNone(self.work.folder)

    def test_the_folder_stays_while_a_run_is_going(self):
        with mock.patch.object(runner.Runner, "running", new=True):
            r = self.choose(self.home / "Cards")
        self.assertEqual(r.status_code, 409)
        self.assertIsNone(self.work.folder)
        self.assertFalse((self.home / "Cards").exists())

    def test_the_browser_lists_folders_only(self):
        (self.home / "b").mkdir()
        (self.home / "A").mkdir()
        (self.home / ".hidden").mkdir()
        (self.home / "scan.png").write_bytes(b"")
        html = self.c.get("/setup/browse", params={"folder": str(self.home)}).text
        listed = re.findall(r"<span>([^<]+)</span></button></li>", html)
        self.assertEqual(listed, ["A", "b"])
        self.assertIn(f"folder={self.home.parent}", html.replace("%2F", "/"))  # up
        self.assertIn(f'data-use="{self.home}"', html)
        top = self.c.get("/setup/browse").text
        self.assertIn("This computer", top)
        self.assertNotIn("data-use", top)  # the top is no folder to use

    def test_an_entry_that_cannot_be_looked_at_does_not_hide_the_others(self):
        class Entry:  # as os.scandir yields them on /mnt/c: pagefile.sys refuses a stat
            def __init__(self, name, error=None):
                self.name, self.path, self.error = name, str(self.home_ / name), error

            def is_dir(self):
                if self.error:
                    raise self.error
                return True

        Entry.home_ = self.home
        found = [
            Entry("Users"),
            Entry("pagefile.sys", PermissionError(13, "denied")),
            Entry("Windows"),
        ]

        class Scan(list):
            def __enter__(self):
                return iter(self)

            def __exit__(self, *exc):
                return False

        with mock.patch("cropdeck.ui.folders.os.scandir", return_value=Scan(found)):
            html = self.c.get("/setup/browse", params={"folder": str(self.home)}).text
        self.assertEqual(
            re.findall(r"<span>([^<]+)</span></button></li>", html), ["Users", "Windows"]
        )
        self.assertEqual(alert(html), [])

    def test_inside_wsl_a_windows_path_is_its_drive_under_mnt(self):
        from cropdeck.ui import wsl

        linux, inside = "Linux version 6.6 generic", "Linux version 6.6 microsoft-standard-WSL2"
        self.assertEqual(wsl.from_windows(r"C:\Users\Dom\Cards", inside), "/mnt/c/Users/Dom/Cards")
        self.assertEqual(wsl.from_windows("D:/", inside), "/mnt/d")
        self.assertEqual(wsl.from_windows(r"C:\Users", linux), r"C:\Users")
        self.assertEqual(wsl.from_windows("/home/dom", inside), "/home/dom")

    def test_a_new_folder_is_made_inside_the_one_shown(self):
        r = self.c.post("/setup/browse/new", data={"parent": str(self.home), "name": "Pokemon"})
        self.assertTrue((self.home / "Pokemon").is_dir())
        self.assertIn(f'data-use="{self.home / "Pokemon"}"', r.text)
        for name, says in (
            ("a/b", "Not a valid folder name."),
            ("Pokemon", "A folder with that name exists."),
        ):
            r = self.c.post("/setup/browse/new", data={"parent": str(self.home), "name": name})
            self.assertEqual(alert(r.text), [says], name)
        self.assertFalse((self.home / "a").exists())


if __name__ == "__main__":
    unittest.main()
