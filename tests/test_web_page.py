import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_BANNED_JS_APIS = ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write")
_EVENT_HANDLER_ATTR_RE = re.compile(r"<[^>]+\son[a-z]+\s*=", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)


class AppJsSafeRenderingTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()

    def test_never_uses_banned_html_injection_apis(self):
        for banned in _BANNED_JS_APIS:
            with self.subTest(api=banned):
                self.assertNotIn(banned, self.source)

    def test_builds_nodes_with_create_element(self):
        self.assertIn("document.createElement", self.source)

    def test_sets_text_with_text_content(self):
        self.assertIn(".textContent", self.source)


class AppJsWriteTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()

    def test_sends_the_session_token_header(self):
        self.assertIn("X-Guild-Token", self.source)

    def test_never_persists_the_token_in_the_browser(self):
        for banned in ("localStorage", "sessionStorage", "document.cookie"):
            with self.subTest(api=banned):
                self.assertNotIn(banned, self.source)

    def test_asks_for_confirmation_before_dismissing(self):
        self.assertIn("window.confirm", self.source)


class IndexHtmlCspComplianceTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "index.html").read_text()

    def test_no_inline_script_bodies(self):
        for attrs, body in _SCRIPT_TAG_RE.findall(self.source):
            with self.subTest(attrs=attrs):
                self.assertIn("src=", attrs)
                self.assertEqual(body.strip(), "")

    def test_no_inline_style_attributes(self):
        self.assertNotIn("style=", self.source)

    def test_no_inline_event_handler_attributes(self):
        self.assertIsNone(_EVENT_HANDLER_ATTR_RE.search(self.source))

    def test_no_external_resources(self):
        self.assertNotIn("http://", self.source)
        self.assertNotIn("https://", self.source)

    def test_references_local_static_assets(self):
        self.assertIn('href="/app.css"', self.source)
        self.assertIn('src="/app.js"', self.source)


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
