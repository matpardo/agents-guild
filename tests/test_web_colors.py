import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_LIFECYCLES = ("needs-human", "converging", "ready", "draft", "merged", "closed")
_TASK_STATES = ("active", "blocked", "queued")
_CHECK_CLASSES = ("checks-failing", "checks-clear", "checks-passing", "checks-pending", "checks-none")


def _dark_block(css):
    start = css.index("prefers-color-scheme: dark")
    return css[start:css.index("\n}\n", start)]


class LifecycleColorTests(unittest.TestCase):
    def setUp(self):
        self.js = (_WEB_DIR / "app.js").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()

    def test_app_js_assigns_a_lifecycle_class(self):
        self.assertIn('"pill lifecycle-" + pr.lifecycle', self.js)

    def test_app_css_defines_one_rule_per_lifecycle(self):
        for lifecycle in _LIFECYCLES:
            with self.subTest(lifecycle=lifecycle):
                rules = re.findall(r"^\.lifecycle-{}\s*\{{".format(re.escape(lifecycle)), self.css, re.M)
                self.assertEqual(len(rules), 1)

    def test_lifecycle_colors_have_a_dark_variant(self):
        dark = _dark_block(self.css)
        for lifecycle in _LIFECYCLES:
            with self.subTest(lifecycle=lifecycle):
                self.assertIn("--lifecycle-{}-fg".format(lifecycle), dark)
                self.assertIn("--lifecycle-{}-bg".format(lifecycle), dark)


class ChecksAndTaskColorTests(unittest.TestCase):
    def setUp(self):
        self.js = (_WEB_DIR / "app.js").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()

    def test_app_js_assigns_check_classes(self):
        for name in _CHECK_CLASSES:
            with self.subTest(name=name):
                self.assertIn(name, self.js)

    def test_app_css_defines_check_classes(self):
        for name in _CHECK_CLASSES:
            with self.subTest(name=name):
                self.assertRegex(self.css, r"(?m)^\.{}\s*\{{".format(name))

    def test_no_checks_label_is_kept(self):
        self.assertIn('"no checks"', self.js)

    def test_app_js_assigns_a_task_state_class(self):
        self.assertIn('"state state-" + task.state', self.js)

    def test_app_css_defines_one_rule_per_task_state(self):
        for task_state in _TASK_STATES:
            with self.subTest(task_state=task_state):
                self.assertRegex(self.css, r"(?m)^\.state-{}\s*\{{".format(task_state))

    def test_task_and_check_colors_have_dark_variants(self):
        dark = _dark_block(self.css)
        for variable in ("--red", "--green", "--blue"):
            with self.subTest(variable=variable):
                self.assertIn(variable + ":", dark)

    def test_page_never_sets_inline_colors(self):
        self.assertNotIn(".style", self.js)
        self.assertNotIn("setAttribute", self.js)


if __name__ == "__main__":
    unittest.main()
