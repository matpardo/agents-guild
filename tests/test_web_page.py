import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_BANNED_JS_APIS = ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write")
_EVENT_HANDLER_ATTR_RE = re.compile(r"<[^>]+\son[a-z]+\s*=", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)


_SCRIPTS = ("app.js", "history.js", "progress.js")
_WRITING_SCRIPTS = ("app.js",)
_PAGES = ("index.html", "history.html", "progress.html")


class PageScriptSafeRenderingTests(unittest.TestCase):
    def test_never_uses_banned_html_injection_apis(self):
        for name in _SCRIPTS:
            source = (_WEB_DIR / name).read_text()
            for banned in _BANNED_JS_APIS:
                with self.subTest(script=name, api=banned):
                    self.assertNotIn(banned, source)

    def test_builds_nodes_with_create_element(self):
        for name in _SCRIPTS:
            with self.subTest(script=name):
                self.assertIn("document.createElement", (_WEB_DIR / name).read_text())

    def test_sets_text_with_text_content(self):
        for name in _SCRIPTS:
            with self.subTest(script=name):
                self.assertIn(".textContent", (_WEB_DIR / name).read_text())

    def test_never_writes_inline_styles_or_handler_attributes(self):
        for name in _SCRIPTS:
            source = (_WEB_DIR / name).read_text()
            with self.subTest(script=name):
                self.assertNotIn(".style", source)
                self.assertNotIn("setAttribute", source)
                self.assertNotIn("eval(", source)
                self.assertNotIn("new Function", source)


class PageScriptWriteTests(unittest.TestCase):
    def test_sends_the_session_token_header(self):
        for name in _WRITING_SCRIPTS:
            with self.subTest(script=name):
                self.assertIn("X-Guild-Token", (_WEB_DIR / name).read_text())

    def test_never_persists_the_token_in_the_browser(self):
        for name in _SCRIPTS:
            source = (_WEB_DIR / name).read_text()
            for banned in ("localStorage", "sessionStorage", "document.cookie"):
                with self.subTest(script=name, api=banned):
                    self.assertNotIn(banned, source)


class AppJsWriteTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()

    def test_notice_buttons_use_the_notice_routes(self):
        self.assertIn('"/api/notices/"', self.source)
        self.assertIn('"/api/notices/seen-all"', self.source)
        for label in ("Mark seen", "Mark unseen", "Mark all seen"):
            with self.subTest(label=label):
                self.assertIn('"{}"'.format(label), self.source)

    def test_asks_for_confirmation_before_dismissing(self):
        self.assertIn("window.confirm", self.source)


class HtmlCspComplianceTests(unittest.TestCase):
    def test_no_inline_script_bodies(self):
        for name in _PAGES:
            for attrs, body in _SCRIPT_TAG_RE.findall((_WEB_DIR / name).read_text()):
                with self.subTest(page=name, attrs=attrs):
                    self.assertIn("src=", attrs)
                    self.assertEqual(body.strip(), "")

    def test_no_inline_style_attributes_or_style_tags(self):
        for name in _PAGES:
            source = (_WEB_DIR / name).read_text()
            with self.subTest(page=name):
                self.assertNotIn("style=", source)
                self.assertNotIn("<style", source)

    def test_no_inline_event_handler_attributes(self):
        for name in _PAGES:
            with self.subTest(page=name):
                self.assertIsNone(_EVENT_HANDLER_ATTR_RE.search((_WEB_DIR / name).read_text()))

    def test_no_external_resources(self):
        for name in _PAGES:
            source = (_WEB_DIR / name).read_text()
            with self.subTest(page=name):
                self.assertNotIn("http://", source)
                self.assertNotIn("https://", source)

    def test_references_local_static_assets(self):
        index = (_WEB_DIR / "index.html").read_text()
        self.assertIn('href="/app.css"', index)
        self.assertIn('src="/app.js"', index)


class AppCssTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.css").read_text()

    def test_supports_dark_mode_via_prefers_color_scheme(self):
        self.assertIn("prefers-color-scheme: dark", self.source)

    def test_is_responsive_down_to_phone_width(self):
        self.assertIn("@media (max-width:", self.source)

    def test_does_not_load_external_fonts(self):
        self.assertNotIn("http://", self.source)
        self.assertNotIn("https://", self.source)
        self.assertNotIn("@font-face", self.source)


if __name__ == "__main__":
    unittest.main()
