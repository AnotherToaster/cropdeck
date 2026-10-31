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


def badge_rules() -> dict[str, str]:
    """kind -> the declarations of the rule that styles the badge itself (not its dot)."""
    css = re.sub(r"/\*.*?\*/", "", (UI / "static" / "app.css").read_text(), flags=re.S)
    looks = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        for sel in selectors.split(","):
            m = re.fullmatch(r'\s*\.badge\[data-kind="([\w-]+)"\]\s*', sel)
            if m:
                looks[m.group(1)] = looks.get(m.group(1), "") + body
    return looks


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
        for path, item in (("/", "Scan"), ("/review", "Review")):
            html = self.c.get(path).text
            self.assertIn('class="site-header"', html, path)
            current = re.search(r'<a href="[^"]*" aria-current="page">\s*([A-Za-z]+)', html)
            self.assertEqual(current.group(1), item, path)
        setup = self.c.get("/setup").text
        settings = re.search(r'<a class="icon-button" href="/setup"[^>]*>', setup)
        self.assertIn('aria-current="page"', settings.group(0))  # setup stands in for settings
        self.assertNotIn("/collection", self.c.get("/").text)  # not built yet: not offered

    def test_the_header_shows_the_folder_and_the_layout(self):
        html = self.c.get("/").text
        self.assertIn("My Cards", html)
        self.assertIn("8 sideways", html)  # the default layout
        self.assertNotIn('class="pill', html)  # nothing to review yet: no count pill

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
        self.assertIn("Not running", self.c.get("/offline").text)


@unittest.skipIf(TestClient is None, 'needs pip install "cropdeck[ui]"')
class Components(unittest.TestCase):
    """Each macro in templates/components, rendered on its own, in every variant."""

    def setUp(self):
        from jinja2 import Environment, FileSystemLoader

        self.env = Environment(loader=FileSystemLoader(str(UI / "templates")), autoescape=True)
        self.env.globals["t"] = i18n.t

    def macro(self, file, name):
        return getattr(self.env.get_template(f"components/{file}.html").module, name)

    def test_every_badge_kind_has_its_words_and_its_look(self):
        kinds = self.env.get_template("components/badge.html").module.KINDS
        handoff = {"waiting", "working", "done", "skipped", "stopped", "needs-backs", "ready",
                   "check", "unread", "filled", "accepted",
                   "scanned", "listed", "sold", "shipped", "keeping"}  # fmt: skip
        self.assertEqual(set(kinds), handoff)
        looks = badge_rules()
        for k in kinds:
            self.assertIn(f'data-kind="{k}"', str(self.macro("badge", "badge")(k)))
            self.assertRegex(looks.get(k, ""), r"color:.*background:", k)  # its own text and ground
            self.assertTrue(i18n.t(f"badge.{k}"))

    def test_the_grey_badges_use_text_colour_for_contrast(self):
        looks = badge_rules()
        for k in ("waiting", "skipped", "filled", "scanned"):
            self.assertIn("color: var(--text)", looks[k], k)

    def test_a_disabled_button_says_why(self):
        html = str(self.macro("button", "button")("No new scans", disabled_reason="No scans yet"))
        self.assertIn("disabled", html)
        self.assertIn("No scans yet", html)

    def test_the_glass_places_cards_where_the_layout_says(self):
        from cropdeck.layouts import LAYOUTS

        html = str(self.macro("glass", "glass")(LAYOUTS["s8"], selected=True))
        self.assertEqual(html.count('class="glass-card"'), 8)
        # card 1 of s8 at 12 mm, 12 mm on the 210 x 297 glass, 88 x 63 mm
        self.assertIn("left: 5.71%; top: 4.04%; width: 41.90%; height: 21.21%", html)
        self.assertIn('data-selected="yes"', html)

    def test_progress_tells_screen_readers_the_real_counts(self):
        html = str(
            self.macro("progress", "progress")([{"fill": 0.5, "label": "Tray 1"}], 4, 8, "Run")
        )
        self.assertIn('role="progressbar"', html)
        self.assertIn('aria-valuenow="4"', html)
        self.assertIn('aria-valuemax="8"', html)
        self.assertIn("width: 50.0%", html)

    def test_fields_show_unsure_and_fixed(self):
        field = self.macro("field", "field")
        self.assertIn("· unsure", str(field("Number", "n", "1/2", "unsure")))
        fixed = str(field("Currency", "c", "CHF", "fixed"))
        self.assertIn('aria-label="Fixed"', fixed)
        self.assertNotIn("<input", fixed)  # fixed is shown, not editable

    def test_an_empty_table_cell_is_an_en_dash(self):
        cols = [{"label": "Name", "num": False}, {"label": "Price", "num": True}]
        html = str(self.macro("table", "table_row")(cols, ["", None]))
        self.assertEqual(html.count("–"), 2)

    def test_a_pair_shows_front_left_of_its_back(self):
        html = str(self.macro("pair", "pair")("017", "f.png", "b.png", "selected"))
        self.assertLess(html.index("f.png"), html.index("b.png"))
        self.assertIn('data-state="selected"', html)

    def test_no_colour_is_hard_coded_outside_the_tokens(self):
        static = UI / "static"
        for f in [*(UI / "templates").rglob("*.html"), static / "app.css", *static.glob("css/*")]:
            self.assertNotRegex(f.read_text(), r"#[0-9A-Fa-f]{6}\b|rgba?\(", f.name)

    def test_the_components_page_is_a_dev_tool_only(self):
        self.assertEqual(client().get("/_components").status_code, 404)
        page = client(dev=True).get("/_components")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.text.count('class="badge"'), 25)


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

    def test_another_address_is_one_named_address_never_every_network(self):
        self.assertIsNone(server.check_host("100.64.0.1"))
        for host in ("0.0.0.0", "::", "atlas"):
            self.assertIsNotNone(server.check_host(host), host)
        self.assertEqual(server.url(8737, "fd7a::1"), "http://[fd7a::1]:8737/")

    def test_the_address_bound_to_is_answered_and_others_still_refused(self):
        c = TestClient(ui_app.create_app(PORT, address="100.64.0.1:8737"))
        ok = c.get("/health", headers={"host": "100.64.0.1:8737"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(c.get("/health", headers={"host": "100.64.0.2:8737"}).status_code, 421)
        post = c.post("/process", headers={"host": "100.64.0.1:8737", "origin": "http://evil"})
        self.assertEqual(post.status_code, 403)


if __name__ == "__main__":
    unittest.main()
