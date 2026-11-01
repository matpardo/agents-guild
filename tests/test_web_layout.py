import re
import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


def _pane_sections(html):
    match = re.search(r'<div class="pane">(.*?)</div>', html, re.DOTALL)
    return re.findall(r'<section id="([a-z-]+)"', match.group(1))


class BoardLayoutTests(unittest.TestCase):
    def setUp(self):
        self.html = (_WEB_DIR / "index.html").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()
        self.js = (_WEB_DIR / "app.js").read_text()

    def test_pane_holds_every_section_in_view_order(self):
        self.assertEqual(
            _pane_sections(self.html),
            [
                "asks",
                "ready-for-you",
                "answered-asks",
                "merge-queues",
                "progress",
                "daily-tasks",
                "parties",
                "memory",
                "adventurers",
                "health-jobs",
                "solo-players",
                "ideas",
                "quest-board",
                "notices",
                "raids",
                "drift",
                "projects",
                "realm",
            ],
        )

    def test_sidebar_sits_beside_the_pane(self):
        main = re.search(r"<main>(.*?)</main>", self.html, re.DOTALL).group(1)
        self.assertLess(main.index('<nav id="sidebar"'), main.index('<div class="pane">'))

    def test_header_keeps_the_state_filter_and_resources_without_party_or_raid_selects(self):
        header = re.search(r"<header>(.*?)</header>", self.html, re.DOTALL).group(1)
        self.assertIn('id="state-filter"', header)
        self.assertIn('<section id="resources"', header)
        self.assertNotIn('id="party-filter"', self.html)
        self.assertNotIn('id="raid-filter"', self.html)
        self.assertIn(".header-row", self.css)

    def test_page_uses_the_full_width_and_stacks_on_narrow_screens(self):
        self.assertIn("max-width: none;", self.css)
        self.assertNotIn("max-width: 60rem", self.css)
        self.assertIn("grid-template-columns: 16rem minmax(0, 1fr);", self.css)
        self.assertIn("@media (min-width: 481px)", self.css)

    def test_notices_collapse_and_keep_their_state_across_refreshes(self):
        self.assertIn("noticesOpen: true", self.js)
        self.assertIn("details.open = state.noticesOpen", self.js)
        self.assertIn("state.noticesOpen = details.open", self.js)


class PrBlockUiTests(unittest.TestCase):
    def setUp(self):
        self.js = (_WEB_DIR / "app.js").read_text()

    def test_pr_card_has_block_and_unblock_actions(self):
        for token in (
            '"Block manually"',
            '"Unblock"',
            '"Relink"',
            '"Untrack"',
            '"relink"',
            '"untrack"',
            "/api/prs/",
            "pr.blocked_external",
            "BLOCKED_EXTERNAL_TEXT",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_pr_card_renders_review_pills_and_stacked_base(self):
        for token in ("pr.review_reasons", "pr.base_branch", "DEFAULT_BRANCHES", '"on " + pr.base_branch'):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_queue_entries_render_the_blocked_external_pill(self):
        self.assertIn('label === "blocked-external"', self.js)
