import shutil
import unittest
from pathlib import Path

from tests import node_harness

_HARNESS_NAME = "web_token_harness.js"
_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebTokenBehaviorTests(unittest.TestCase):
    def _load(self, script, hash_value, stored):
        return node_harness.request(
            _HARNESS_NAME, {"src": str(_WEB_DIR / script), "hash": hash_value, "stored": stored}
        )

    def test_fragment_token_is_stored_stripped_and_sent_on_reads(self):
        result = self._load("app.js", "#t=abc_123-X", None)
        self.assertEqual(result["saved"], {"guild-token": "abc_123-X"})
        self.assertEqual(result["replaced"], ["/"])
        self.assertIn("abc_123-X", result["getHeaders"])
        self.assertEqual(set(result["getHeaders"]), {"abc_123-X"})

    def test_stored_token_is_used_when_the_url_has_no_fragment(self):
        result = self._load("app.js", "", "kept")
        self.assertEqual(result["saved"], {})
        self.assertEqual(result["replaced"], [])
        self.assertEqual(set(result["getHeaders"]), {"kept"})

    def test_view_fragment_is_not_taken_for_a_token(self):
        result = self._load("app.js", "#party/alpha", "kept")
        self.assertEqual(result["saved"], {})
        self.assertEqual(set(result["getHeaders"]), {"kept"})
