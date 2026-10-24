import json
import shutil
import unittest

from tests import node_harness
from tests.test_web_drift import _APP_JS_PATH, _BOARD, _HARNESS_NAME


def _render(board, hash_value, out_id, mode):
    return node_harness.request(_HARNESS_NAME, {
        "src": str(_APP_JS_PATH), "data": board, "hash": hash_value, "outId": out_id, "mode": mode,
    })


def _entry(number, party):
    return {
        "ref": "o/r#" + str(number), "repo": "o/r", "number": number, "party": party, "task": "q/T1", "lifecycle": "ready",
        "branch": "b" + str(number), "checks_failing": 0, "checks_passing": 1, "checks_pending": 0, "labels": [],
        "url": "https://example.test/" + str(number), "position": number, "unblocks": 0, "state": "ready", "next_action": False,
        "action": "merge", "why": "ready", "reasons": [], "blockers": [], "waits": [], "gates": [],
        "human_state": "ready", "human_missing": [], "notes": [],
    }


def _queue(scope, entries):
    return {"head": None, "scope": scope, "synced_at": "now", "synced_label": "synced now", "main": [], "queue": entries}


def _party(name, raids):
    party = dict(_BOARD["parties"][0], name=name)
    party["raids"] = [{"raid": raid} for raid in raids]
    return party


_VIEWS_BOARD = dict(
    _BOARD,
    raids=[{"name": "r", "members": ["a", "b"], "paused": True}, {"name": "r2", "members": ["b"], "paused": False}],
    parties=[_party("a", ["r"]), _party("b", ["r", "r2"]), _party("d", [])],
    merge_queues=[
        _queue("raid:r", [_entry(1, "a"), _entry(2, "b")]),
        _queue("raid:r2", [_entry(3, "b")]),
        _queue("party:d", [_entry(4, "d")]),
    ],
)

_PANE_IDS = {
    "asks", "ready-for-you", "answered-asks", "notices", "ideas", "adventurers", "health-jobs",
    "memory", "raids", "drift", "projects", "quest-board", "merge-queues", "parties",
}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebViewBehaviorTests(unittest.TestCase):
    def _queues(self, hash_value):
        return _render(_VIEWS_BOARD, hash_value, "merge-queues", "text")

    def _hidden(self, hash_value):
        return set(json.loads(_render(_VIEWS_BOARD, hash_value, "asks", "hidden")))

    def test_party_in_a_raid_sees_the_whole_raid_queue(self):
        text = self._queues("#party/a")
        self.assertIn("o/r#1", text)
        self.assertIn("o/r#2", text)
        self.assertNotIn("o/r#3", text)
        self.assertNotIn("o/r#4", text)

    def test_party_in_two_raids_sees_both_raid_queues(self):
        text = self._queues("#party/b")
        for ref in ("o/r#1", "o/r#2", "o/r#3"):
            with self.subTest(ref=ref):
                self.assertIn(ref, text)
        self.assertNotIn("o/r#4", text)

    def test_solo_party_sees_its_own_queue(self):
        text = self._queues("#party/d")
        self.assertIn("o/r#4", text)
        self.assertNotIn("o/r#1", text)

    def test_raid_view_shows_only_that_raid_queue(self):
        text = self._queues("#raid/r2")
        self.assertIn("o/r#3", text)
        self.assertNotIn("o/r#1", text)

    def test_sidebar_groups_parties_by_raid_then_solo(self):
        text = _render(_VIEWS_BOARD, "", "sidebar", "text")
        self.assertEqual(text.count("raid r"), 2)
        self.assertLess(text.index("raid r "), text.index("raid r2"))
        self.assertLess(text.index("raid r2"), text.index("solo"))
        self.assertLess(text.index("solo"), text.index("adventurers (0)"))
        self.assertEqual(text.count("paused"), 1)

    def test_sidebar_lists_a_party_in_two_raids_twice_and_solo_once(self):
        tree = json.loads(_render(_VIEWS_BOARD, "", "sidebar", "tree"))
        links = []

        def walk(node):
            if node["tag"] == "a":
                links.append(node["text"])
            for child in node["children"]:
                walk(child)

        walk(tree)
        self.assertEqual(links.count("b"), 2)
        self.assertEqual(links.count("a"), 1)
        self.assertEqual(links.count("d"), 1)

    def test_sidebar_counts(self):
        board = dict(_VIEWS_BOARD, ideas=[{}, {}], adventurers=[{"state": "active"}, {"state": "done"}], new_notice_count=3)
        text = _render(board, "", "sidebar", "text")
        self.assertIn("ideas (2)", text)
        self.assertIn("adventurers (1)", text)
        self.assertIn("overview (3 new)", text)

    def test_needs_you_is_the_default_for_empty_and_unknown_hashes(self):
        expected = _PANE_IDS - {"asks", "ready-for-you", "answered-asks"}
        for hash_value in ("", "#nonsense", "#party", "#party/"):
            with self.subTest(hash=hash_value):
                self.assertEqual(self._hidden(hash_value), expected)

    def test_party_view_hides_every_section_it_does_not_list(self):
        self.assertEqual(self._hidden("#party/a"), _PANE_IDS - {"asks", "merge-queues", "parties", "memory"})

    def test_other_views_hide_their_complement(self):
        shown = {
            "#adventurers": {"adventurers", "health-jobs"},
            "#ideas": {"ideas"},
            "#quests": {"quest-board"},
            "#overview": {"notices", "raids", "drift", "projects"},
            "#raid/r": {"asks", "merge-queues", "parties", "memory"},
        }
        for hash_value, ids in shown.items():
            with self.subTest(hash=hash_value):
                self.assertEqual(self._hidden(hash_value), _PANE_IDS - ids)


if __name__ == "__main__":
    unittest.main()
