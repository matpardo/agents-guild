import re
import unittest
from pathlib import Path

_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.MULTILINE)
_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


class ActionPinTests(unittest.TestCase):
    def test_every_action_is_pinned_by_commit_sha(self):
        refs = [ref for workflow in _WORKFLOWS_DIR.glob("*.yml") for ref in _USES.findall(workflow.read_text())]
        self.assertTrue(refs)
        self.assertEqual([ref for ref in refs if not _PINNED.match(ref)], [])
