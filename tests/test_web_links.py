import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


class PrAndCardLinkRenderingTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()

    def test_links_open_in_a_new_tab_without_leaking_the_opener(self):
        self.assertIn('anchor.target = "_blank"', self.source)
        self.assertIn('anchor.rel = "noopener noreferrer"', self.source)

    def test_pr_url_is_rendered_as_a_link(self):
        self.assertIn("link(pr.url,", self.source)

    def test_card_url_is_rendered_as_a_link_only_when_present(self):
        self.assertIn("if (task.card_url) {", self.source)
        self.assertIn("link(task.card_url,", self.source)


class RaidFilterTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()

    def test_raid_filter_narrows_parties_asks_and_notices(self):
        self.assertIn("function applyRaidFilter(data) {", self.source)
        self.assertIn("members.indexOf(ask.party)", self.source)
        self.assertIn("members.indexOf(party.name)", self.source)
        self.assertIn("notice.scope === scope", self.source)


if __name__ == "__main__":
    unittest.main()
