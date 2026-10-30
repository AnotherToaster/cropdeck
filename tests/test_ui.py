"""Tests for the browser interface (cropdeck ui). Skipped where the ui extra is not installed."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient

    from cropdeck.ui import app as ui_app
    from cropdeck.ui import i18n, server
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
