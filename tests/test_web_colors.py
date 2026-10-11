import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_LIFECYCLES = (
    "fixes-main",
    "fixes-flaky",
    "needs-ask-answer",
    "needs-human-pr-review",
    "blocked-external",
    "converging",
    "ready",
    "draft",
    "merged",
    "closed",
)
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

    def test_app_js_renders_the_flag_badges_and_filters_on_them(self):
        for token in ("lifecycle-needs-ask-answer", "lifecycle-needs-human-pr-review", "pr.needs_ask_answer",
                      "pr.needs_human_pr_review"):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_state_filter_offers_both_flags_and_not_the_old_lifecycle(self):
        html = (_WEB_DIR / "index.html").read_text()
        self.assertIn('<option value="needs-ask-answer">', html)
        self.assertIn('<option value="needs-human-pr-review">', html)
        self.assertNotIn("needs-human\"", html)

    def test_app_js_renders_the_urgency_marks_and_filters_on_them(self):
        for token in ("lifecycle-fixes-main", "lifecycle-fixes-flaky", "pr.fixes_main", "pr.fixes_flaky"):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_state_filter_offers_the_urgency_marks(self):
        html = (_WEB_DIR / "index.html").read_text()
        self.assertIn('<option value="fixes-main">', html)
        self.assertIn('<option value="fixes-flaky">', html)

    def test_app_js_renders_the_branch_span(self):
        self.assertIn('className = "branch"', self.js)

    def test_app_js_has_no_pr_type_chip(self):
        self.assertNotIn("pr-type", self.js)

    def test_app_css_defines_the_branch_style_in_both_schemes(self):
        self.assertEqual(len(re.findall(r"^\.branch\s*\{", self.css, re.M)), 1)
        for name in ("--branch-fg",):
            with self.subTest(name=name):
                self.assertIn(name, self.css)
                self.assertIn(name, _dark_block(self.css))

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


class RoleBadgeTests(unittest.TestCase):
    def setUp(self):
        self.js = (_WEB_DIR / "app.js").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()

    def test_app_js_renders_role_badge_with_modifiers(self):
        for token in ("role-badge", "role-lead", "role-member", "role-solo"):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_app_css_defines_role_rules(self):
        for name in ("role-badge", "role-lead", "role-member", "role-solo"):
            with self.subTest(name=name):
                self.assertRegex(self.css, r"(?m)^\.{}\s*\{{".format(name))

    def test_role_colors_defined_in_both_themes(self):
        dark = _dark_block(self.css)
        light = self.css[:self.css.index("prefers-color-scheme: dark")]
        for role in ("lead", "member", "solo"):
            for suffix in ("fg", "bg"):
                variable = "--role-{}-{}:".format(role, suffix)
                with self.subTest(variable=variable):
                    self.assertIn(variable, light)
                    self.assertIn(variable, dark)


if __name__ == "__main__":
    unittest.main()
