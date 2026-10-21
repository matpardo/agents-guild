import json
import shutil
import subprocess
import unittest
from pathlib import Path

_POLL_HARNESS = Path(__file__).resolve().parent / "web_poll_harness.js"
_APP_JS = Path(__file__).resolve().parent.parent / "guild" / "web" / "app.js"


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPollBehaviorTests(unittest.TestCase):
    def _after_poll(self, scenario):
        result = subprocess.run(
            ["node", str(_POLL_HARNESS), str(_APP_JS), scenario],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(result.stdout)

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
