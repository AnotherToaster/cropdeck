"""Tests for the browser interface (cropdeck ui). Skipped where the ui extra is not installed."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient

    from cropdeck.ui import app as ui_app
    from cropdeck.ui import i18n, server, session
except (ImportError, RuntimeError):  # the ui extra (or httpx for tests) is not installed
    TestClient = None

UI = ROOT / "cropdeck" / "ui"
PORT = 8737


def client(**kw):
    return TestClient(ui_app.create_app(PORT, hosts=("testserver",), **kw))


def tokens(theme: str) -> dict[str, str]:
    """The colour tokens of tokens.css as the browser resolves them for a theme."""
    css = (UI / "static" / "tokens.css").read_text()
    light = css.split("@media")[0]
    found = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", light))
    if theme == "dark":
        dark = css[css.index(':root[data-theme="dark"]') :]
        found.update(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", dark))
    return found


def contrast(a: str, b: str) -> float:
    def lum(hex_):
        c = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Foundations(unittest.TestCase):
    def test_the_page_and_health_answer(self):
        c = client()
        self.assertEqual(c.get("/health").text, ui_app.HEALTH)
        page = c.get("/")
        self.assertEqual(page.status_code, 200)
        for asset in ("/static/tokens.css", "/static/app.css", "/static/js/htmx.min.js"):
            self.assertIn(asset, page.text)
            self.assertEqual(c.get(asset).status_code, 200, asset)
        self.assertEqual(c.get("/static/fonts/Inter-600.woff2").status_code, 200)

    def test_only_this_computer_is_answered(self):
        c = client()
        self.assertEqual(c.get("/", headers={"host": "evil.example:8737"}).status_code, 421)
        foreign = {"origin": "https://evil.example"}
        self.assertEqual(c.post("/health", headers=foreign).status_code, 403)
        own = {"origin": f"http://127.0.0.1:{PORT}"}
        self.assertNotEqual(c.post("/health", headers=own).status_code, 403)

    def test_nothing_is_loaded_from_the_internet(self):
        ours = [*(UI / "templates").rglob("*.html"), *(UI / "static").glob("*.css")]
        for f in ours:
            self.assertNotRegex(f.read_text(), r"https?://", f.name)

    def test_the_theme_follows_the_os_and_dev_mode_can_force_it(self):
        self.assertNotIn("data-theme", client().get("/").text)
        self.assertNotIn("data-theme", client().get("/?theme=dark").text)  # not outside dev mode
        self.assertIn('data-theme="dark"', client(dev=True).get("/?theme=dark").text)

    def test_text_is_readable_in_both_themes(self):
        # every pair the design sets text in, at the WCAG minimum for body text
        pairs = [
            ("text", "bg"),
            ("text", "panel"),
            ("muted", "bg"),
            ("muted", "panel"),
            ("text", "wait-bg"),  # waiting, skipped, scanned badges (chief, 30.10.2026)
            ("on-teal", "teal"),
            ("teal", "bg"),
            ("teal", "teal-soft"),
            ("amber-ink", "amber-soft"),
            ("good-ink", "good-soft"),
            ("problem", "problem-soft"),
        ]
        for theme in ("light", "dark"):
            c = tokens(theme)
            for fg, bg in pairs:
                ratio = contrast(c[fg], c[bg])
                self.assertGreaterEqual(ratio, 4.5, f"{theme}: {fg} on {bg} is {ratio:.2f}")

    def test_every_string_comes_from_the_language_file(self):
        self.assertEqual(i18n.t("app.name"), "cropdeck")
        with self.assertRaises(KeyError):
            i18n.t("app.nothing_written_here")


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Shell(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()) / "My Cards"
        self.folder.mkdir()
        self.config = self.folder.parent / "config" / "ui.json"
        self.c = client(work=session.load(self.folder, self.config))

    def test_every_screen_sits_in_the_shell_with_its_nav_item_current(self):
        for path, item in (("/", "Scan"), ("/review", "Review"), ("/collection", "Collection")):
            html = self.c.get(path).text
            self.assertIn('class="site-header"', html, path)
            current = re.search(r'<a href="[^"]*" aria-current="page">\s*([A-Za-z]+)', html)
            self.assertEqual(current.group(1), item, path)
        self.assertIn('aria-current="page"', self.c.get("/settings").text)

    def test_the_header_shows_the_folder_and_the_layout(self):
        html = self.c.get("/").text
        self.assertIn("My Cards", html)
        self.assertIn("8 sideways", html)  # the default layout
        self.assertNotIn('class="pill', html)  # nothing to review yet: no count pill

    def test_setup_has_the_reduced_header_and_no_nav(self):
        html = self.c.get("/setup").text
        self.assertIn("Runs on this computer only. No account, works offline.", html)
        self.assertNotIn('<nav class="nav"', html)

    def test_without_a_folder_the_first_stop_is_setup(self):
        empty = Path(tempfile.mkdtemp()) / "ui.json"
        c = client(work=session.load(None, empty))
        r = c.get("/", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/setup"))

    def test_the_folder_is_remembered_for_next_time(self):
        self.assertEqual(session.load(None, self.config).folder, self.folder.resolve())

    def test_the_app_window_files_are_served(self):
        manifest = self.c.get("/manifest.webmanifest")
        self.assertEqual(manifest.headers["content-type"], "application/manifest+json")
        for icon in json.loads(manifest.text)["icons"]:
            self.assertEqual(self.c.get(icon["src"]).status_code, 200, icon["src"])
        sw = self.c.get("/sw.js").text
        self.assertIn('"/offline"', sw)
        self.assertNotIn('"/"', sw)  # app pages are never kept: nothing stale shown as current
        self.assertIn("cropdeck is not running", self.c.get("/offline").text)


class Layouts(unittest.TestCase):
    def test_the_layouts_are_the_designs_table(self):
        from cropdeck.layouts import DEFAULT, LAYOUTS

        table = {  # docs/ui/HANDOFF.md, "Glass layouts" (mm)
            "s8": (True, (12, 110), (12, 83, 154, 225)),
            "s6": (True, (12, 110), (30, 117, 204)),
            "u6": (False, (6, 73.5, 141), (30, 130)),
            "u9": (False, (6, 73.5, 141), (6, 104, 202)),
        }
        got = {k: (v.sideways, v.xs, v.ys) for k, v in LAYOUTS.items()}
        self.assertEqual(got, table)
        self.assertEqual((DEFAULT, LAYOUTS[DEFAULT].count), ("s8", 8))
        for lay in LAYOUTS.values():  # every card on the A4 glass
            w, h = lay.card
            self.assertLessEqual(max(lay.xs) + w, 210, lay.id)
            self.assertLessEqual(max(lay.ys) + h, 297, lay.id)

    def test_cropdeck_run_expects_the_default_layouts_count(self):
        from cropdeck.cli import _parser

        self.assertEqual(_parser().parse_args(["run"]).expect, 8)


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Launcher(unittest.TestCase):
    def test_inside_wsl_the_windows_browser_is_used(self):
        cmd = server.browser_command("http://127.0.0.1:8737/", "Linux version 6.6 microsoft WSL2")
        self.assertEqual(cmd[1:], ["/c", "start", "", "http://127.0.0.1:8737/"])
        self.assertIsNone(server.browser_command("http://x/", "Linux version 6.6 generic"))

    def test_a_taken_port_is_not_free(self):
        import socket

        with socket.socket() as s:
            s.bind((server.HOST, 0))
            s.listen()
            self.assertFalse(server.free(s.getsockname()[1]))


if __name__ == "__main__":
    unittest.main()
