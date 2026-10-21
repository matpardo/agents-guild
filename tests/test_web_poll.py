import shutil
import unittest
from pathlib import Path

from tests import node_harness

_POLL_HARNESS_NAME = "web_poll_harness.js"
_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPollBehaviorTests(unittest.TestCase):
    def _after_poll(self, scenario):
        return node_harness.request(_POLL_HARNESS_NAME, {"src": str(_APP_JS), "scenario": scenario})

    def test_poll_with_unchanged_ideas_keeps_the_idea_form_node(self):
        after = self._after_poll("same")
        self.assertTrue(after["sameNode"])
        self.assertEqual(after["value"], "half typed")

    def test_poll_with_changed_ideas_restores_focus_and_caret_in_the_idea_form(self):
        after = self._after_poll("changed")
        self.assertFalse(after["sameNode"])
        self.assertTrue(after["focused"])
        self.assertEqual(after["selection"], [4, 4])
        self.assertEqual(after["value"], "half typed")
