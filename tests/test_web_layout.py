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

    def test_left_column_holds_asks_notices_and_drift(self):
        self.assertEqual(_column(self.html, "left"), ["asks", "notices", "drift"])

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
