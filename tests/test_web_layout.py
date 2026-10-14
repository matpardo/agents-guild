import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


def _column(html, name):
    match = re.search(r'<div class="column column-{}">(.*?)</div>'.format(name), html, re.DOTALL)
    return re.findall(r'<section id="([a-z-]+)"', match.group(1))


class BoardLayoutTests(unittest.TestCase):
    def setUp(self):
        self.html = (_WEB_DIR / "index.html").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()
        self.js = (_WEB_DIR / "app.js").read_text()

    def test_left_column_holds_asks_notices_drift_and_projects(self):
        self.assertEqual(_column(self.html, "left"), ["asks", "answered-asks", "notices", "memory", "raids", "drift", "projects"])

    def test_header_row_holds_resources_beside_the_filters(self):
        header = re.search(r"<header>(.*?)</header>", self.html, re.DOTALL).group(1)
        self.assertIn('id="filters"', header)
        self.assertIn('<section id="resources"', header)
        self.assertIn(".header-row", self.css)

    def test_right_column_holds_merge_queue_then_parties(self):
        self.assertEqual(_column(self.html, "right"), ["merge-queues", "parties"])

    def test_columns_sit_side_by_side_on_wide_screens(self):
        self.assertIn(".column-right", self.css)
        self.assertNotIn("grid-row: 1 / span 4", self.css)

    def test_notices_collapse_and_keep_their_state_across_refreshes(self):
        self.assertIn("noticesOpen: true", self.js)
        self.assertIn("details.open = state.noticesOpen", self.js)
        self.assertIn("state.noticesOpen = details.open", self.js)


class PrBlockUiTests(unittest.TestCase):
    def setUp(self):
        self.js = (_WEB_DIR / "app.js").read_text()

    def test_pr_card_has_block_and_unblock_actions(self):
        for token in ('"Block manually"', '"Unblock"', "/api/prs/", "pr.blocked_external", "BLOCKED_EXTERNAL_TEXT"):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_pr_card_renders_review_pills_and_stacked_base(self):
        for token in ("pr.review_reasons", "pr.base_branch", "DEFAULT_BRANCHES", '"on " + pr.base_branch'):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_queue_entries_render_the_blocked_external_pill(self):
        self.assertIn('label === "blocked-external"', self.js)
