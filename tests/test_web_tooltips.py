import re
import unittest
from pathlib import Path

from guild import merge_queue
from guild.commands import board

_ROOT = Path(__file__).resolve().parent.parent
_APP_JS = (_ROOT / "guild" / "web" / "app.js").read_text()
_DRIFT_PY = (_ROOT / "guild" / "commands" / "drift.py").read_text()
_TOOLTIPS_BLOCK_RE = re.compile(r"var TOOLTIPS = deepFreeze\(\{\n(.*?)\n  \}\);", re.DOTALL)
_GROUP_RE = re.compile(r"^    (\w+): \{\n(.*?)\n    \},?$", re.DOTALL | re.MULTILINE)
_KEY_RE = re.compile(r'^      "?([^":]+)"?:', re.MULTILINE)
_DRIFT_RULE_RE = re.compile(r'\("([^"]+)",\s*_rule_')
_DRIFT_EXTRA_RULE = "party has no running leader"


def _groups():
    block = _TOOLTIPS_BLOCK_RE.search(_APP_JS)
    if block is None:
        return {}
    return {
        name: set(_KEY_RE.findall(body))
        for name, body in _GROUP_RE.findall(block.group(1))
    }


class TooltipCoverageTests(unittest.TestCase):
    def setUp(self):
        self.groups = _groups()

    def assertCovers(self, group, expected):
        self.assertIn(group, self.groups)
        self.assertEqual(set(expected) - self.groups[group], set())

    def test_party_statuses(self):
        self.assertCovers("partyStatus", board._STATUS_STYLES)

    def test_pr_lifecycles(self):
        self.assertCovers("lifecycle", board._LIFECYCLE_STYLES)

    def test_pr_flags(self):
        self.assertCovers("flag", [name for _, name, _ in board._FLAG_STYLES])

    def test_queue_states(self):
        self.assertCovers(
            "queueState",
            [merge_queue._READY_STATE, merge_queue._WAITING_STATE, merge_queue._BLOCKED_STATE],
        )

    def test_queue_actions(self):
        self.assertCovers(
            "queueAction",
            [merge_queue._MERGE_ACTION, merge_queue._PROMOTE_ACTION, "review", "fix", "wait"],
        )

    def test_task_states(self):
        self.assertCovers("taskState", ["queued", "active", "blocked", "done"])

    def test_party_states(self):
        self.assertCovers("partyState", ["active", "awaiting-leader", "closed"])

    def test_checks(self):
        self.assertCovers("checks", ["failing", "passing", "pending", "none"])

    def test_scopes(self):
        self.assertCovers("scope", ["guild", "project", "raid"])

    def test_roles(self):
        self.assertCovers("role", ["solo", "lead", "member"])

    def test_blocked_waits(self):
        self.assertCovers("blockedWait", ["permission"])

    def test_drift_rules(self):
        rules = _DRIFT_RULE_RE.findall(_DRIFT_PY) + [_DRIFT_EXTRA_RULE]
        self.assertGreater(len(rules), 1)
        self.assertCovers("drift", rules)

    def test_standalone_labels(self):
        self.assertCovers(
            "ui",
            [
                "noticeNew", "issued", "timeLeft", "askBlocks", "mainRed",
                "generation", "leader", "noLeader", "claims", "synced",
            ],
        )


class TooltipUsageTests(unittest.TestCase):
    def test_helper_sets_only_the_title_property(self):
        self.assertIn(".title = ", _APP_JS)

    def test_filters_are_explained_in_the_page(self):
        index = (_ROOT / "guild" / "web" / "index.html").read_text()
        self.assertEqual(len(re.findall(r"<label title=", index)), 3)


if __name__ == "__main__":
    unittest.main()
