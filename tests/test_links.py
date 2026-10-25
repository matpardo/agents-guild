import unittest

from guild import links


class LinksTests(unittest.TestCase):
    def test_pr_url(self):
        self.assertEqual(links.pr_url("acme/app", 41), "https://github.com/acme/app/pull/41")

    def test_card_url_joins_browse_url_and_key(self):
        config = {"tracker": {"browse_url": "https://tracker.example.com/browse/"}}
        self.assertEqual(links.card_url(config, "PROJ-12"), "https://tracker.example.com/browse/PROJ-12")

    def test_card_url_is_none_without_key_config_tracker_or_browse_url(self):
        config = {"tracker": {"browse_url": "https://tracker.example.com/browse/"}}
        self.assertIsNone(links.card_url(config, None))
        self.assertIsNone(links.card_url(None, "PROJ-12"))
        self.assertIsNone(links.card_url({}, "PROJ-12"))
        self.assertIsNone(links.card_url({"tracker": {}}, "PROJ-12"))


if __name__ == "__main__":
    unittest.main()
