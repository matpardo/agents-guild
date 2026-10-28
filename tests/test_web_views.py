import json
import shutil
import unittest

from tests import node_harness
from tests.test_web_drift import _APP_JS_PATH, _BOARD, _HARNESS_NAME


def _render(board, hash_value, out_id, mode):
    return node_harness.request(
        _HARNESS_NAME,
        {
            "src": str(_APP_JS_PATH),
            "data": board,
            "hash": hash_value,
            "outId": out_id,
            "mode": mode,
        },
    )


def _entry(number, party):
    return {
        "ref": "o/r#" + str(number),
        "repo": "o/r",
        "number": number,
        "party": party,
        "task": "q/T1",
        "lifecycle": "ready",
        "branch": "b" + str(number),
        "checks_failing": 0,
        "checks_passing": 1,
        "checks_pending": 0,
        "labels": [],
        "url": "https://example.test/" + str(number),
        "position": number,
        "unblocks": 0,
        "state": "ready",
        "next_action": False,
        "action": "merge",
        "why": "ready",
        "reasons": [],
        "blockers": [],
        "waits": [],
        "gates": [],
        "human_state": "ready",
        "human_missing": [],
        "notes": [],
    }


def _queue(scope, entries):
    return {
        "head": None,
        "scope": scope,
        "synced_at": "now",
        "synced_label": "synced now",
        "main": [],
        "queue": entries,
    }


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
    "asks",
    "ready-for-you",
    "answered-asks",
    "notices",
    "ideas",
    "adventurers",
    "health-jobs",
    "memory",
    "raids",
    "drift",
    "projects",
    "quest-board",
    "merge-queues",
    "progress",
    "daily-tasks",
    "parties",
    "realm",
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

    def _progress(self, hash_value, mode):
        def party(name, raids, quests, blocked, groups):
            remaining = {"quests": quests, "active": 1, "blocked": blocked, "queued": 2}
            return dict(_party(name, raids), remaining=remaining, blocked_groups=groups)

        parties = [
            party("a", ["r"], [{"slug": "x", "done": 1, "total": 4}], 2, [{"reason": "ci", "tids": ["x/T1", "x/T2"]}]),
            party("b", ["r"], [{"slug": "y", "done": 3, "total": 4}], 1, [{"reason": "ci", "tids": ["y/T1"]}]),
            party("c", ["r"], [], 0, []),
        ]
        board = dict(_VIEWS_BOARD, parties=parties + [party("d", [], [], 0, [])])
        return _render(board, hash_value, "progress", mode)

    def test_party_view_shows_its_progress(self):
        self.assertEqual(
            self._progress("#party/a", "text").split(),
            "progress 1/4 tasks done (25%) x 1/4 active 1 · blocked 2 · queued 2 2 blocked — ci".split(),
        )

    def test_raid_view_sums_progress_and_merges_blocked_groups(self):
        self.assertEqual(
            self._progress("#raid/r", "text").split(),
            "progress 4/8 tasks done (50%) x 1/4 y 3/4 active 2 · blocked 3 · queued 4 3 blocked — ci".split(),
        )

    def test_party_without_quests_shows_no_active_quest(self):
        self.assertEqual(self._progress("#party/c", "text").split(), ["progress", "no", "active", "quest"])

    def test_blocked_group_lists_its_tasks_in_a_tooltip(self):
        self.assertIn('"title": "x/T1, x/T2"', self._progress("#party/a", "tree").replace('":"', '": "'))

    def _daily_tasks_text(self, hash_value):
        def days(created, done, active):
            return [
                {"day": "2026-10-2{}".format(index), "created": created, "done": done, "active": flag, "existed": True}
                for index, flag in zip((4, 5), active, strict=True)
            ]

        parties = [
            dict(_party("a", ["r"]), daily_tasks=days(1, 0, (True, False))),
            dict(_party("b", ["r"]), daily_tasks=days(2, 3, (False, False))),
            dict(_party("c", ["r"]), daily_tasks=days(0, 0, (False, False))),
        ]
        board = dict(_VIEWS_BOARD, parties=parties + [dict(_party("d", []), daily_tasks=days(7, 7, (True, True)))])
        return _render(board, hash_value, "daily-tasks", "text").split()

    def test_party_view_shows_its_daily_tasks(self):
        self.assertEqual(
            self._daily_tasks_text("#party/a"),
            ["tasks", "per", "day", "day", "10-24", "10-25", "created", "1", "1", "done", "0", "-"],
        )

    def test_raid_view_sums_the_daily_tasks_of_its_members(self):
        self.assertEqual(
            self._daily_tasks_text("#raid/r"),
            ["tasks", "per", "day", "day", "10-24", "10-25", "created", "3", "3", "done", "3", "3"],
        )

    def test_party_view_marks_days_without_a_session(self):
        self.assertEqual(
            self._daily_tasks_text("#party/c"),
            ["tasks", "per", "day", "day", "10-24", "10-25", "created", "-", "-", "done", "-", "-"],
        )

    def test_dash_cells_explain_themselves_in_a_tooltip(self):
        board = dict(
            _VIEWS_BOARD,
            parties=[
                dict(
                    _party("a", []),
                    daily_tasks=[{"day": "2026-10-24", "created": 0, "done": 0, "active": False, "existed": True}],
                )
            ],
        )
        tree = json.loads(_render(board, "#party/a", "daily-tasks", "tree"))
        titles = []

        def walk(node):
            if node["text"] == "-":
                titles.append(node["title"])
            for child in node["children"]:
                walk(child)

        walk(tree)
        self.assertEqual(len(titles), 2)
        self.assertTrue(all("idle across midnight" in title for title in titles))

    def _missing_day_tree(self, hash_value):
        def day(existed):
            return {"day": "2026-10-24", "created": 0, "done": 0, "active": False, "existed": existed}

        board = dict(
            _VIEWS_BOARD,
            parties=[
                dict(_party("a", ["r"]), daily_tasks=[day(False)]),
                dict(_party("b", ["r"]), daily_tasks=[day(True)]),
            ],
        )
        return _render(board, hash_value, "daily-tasks", "tree")

    def test_days_before_the_party_existed_show_x_with_a_tooltip(self):
        tree = json.loads(self._missing_day_tree("#party/a"))
        titles = []

        def walk(node):
            if node["text"] == "x":
                titles.append(node["title"])
            for child in node["children"]:
                walk(child)

        walk(tree)
        self.assertEqual(titles, ["party did not exist yet"] * 2)

    def test_raid_day_exists_when_any_member_existed(self):
        self.assertNotIn('"text": "x"', self._missing_day_tree("#raid/r").replace('":"', '": "'))

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
        board = dict(
            _VIEWS_BOARD, ideas=[{}, {}], adventurers=[{"state": "active"}, {"state": "done"}], new_notice_count=3
        )
        text = _render(board, "", "sidebar", "text")
        self.assertIn("ideas (2)", text)
        self.assertIn("adventurers (1)", text)
        self.assertIn("overview (3 new)", text)

    def test_needs_you_counts_above_zero_are_pills_by_type(self):
        board = dict(_VIEWS_BOARD, asks=[{"party": "a"}], ready_for_you=[], blocked=[{}, {}])
        nodes = _walk(json.loads(_render(board, "", "sidebar", "tree")), [])
        pairs = [(node["text"], node["className"]) for node in nodes]
        for pair in (
            ("1 asks", "pill needs-asks"),
            ("2 blocked", "pill needs-blocked"),
            ("0 ready", "muted"),
            ("0 context high", "muted"),
        ):
            with self.subTest(pair=pair):
                self.assertIn(pair, pairs)

    def test_needs_you_is_the_default_for_empty_and_unknown_hashes(self):
        expected = _PANE_IDS - {"asks", "ready-for-you", "answered-asks"}
        for hash_value in ("", "#nonsense", "#party", "#party/"):
            with self.subTest(hash=hash_value):
                self.assertEqual(self._hidden(hash_value), expected)

    def test_party_view_hides_every_section_it_does_not_list(self):
        self.assertEqual(
            self._hidden("#party/a"),
            _PANE_IDS - {"asks", "merge-queues", "progress", "daily-tasks", "parties", "memory"},
        )

    def test_other_views_hide_their_complement(self):
        shown = {
            "#adventurers": {"adventurers", "health-jobs"},
            "#ideas": {"ideas"},
            "#quests": {"quest-board"},
            "#overview": {"notices", "raids", "drift", "projects", "realm"},
            "#raid/r": {"asks", "merge-queues", "progress", "daily-tasks", "parties", "memory"},
        }
        for hash_value, ids in shown.items():
            with self.subTest(hash=hash_value):
                self.assertEqual(self._hidden(hash_value), _PANE_IDS - ids)


def _state_party(name, raids, status, **extra):
    party = _party(name, raids)
    party["status"] = {"name": status, "label": status}
    party["remaining"] = {"all_done": False, "pending": 2, "extra_prs": 0, "quests": []}
    party.update(extra)
    return party


def _walk(node, found):
    found.append(node)
    for child in node["children"]:
        _walk(child, found)
    return found


_STATE_BOARD = dict(
    _BOARD,
    raids=[{"name": "r", "members": ["w", "q", "k"], "paused": False}],
    parties=[
        _state_party("w", ["r"], "working"),
        _state_party("q", ["r"], "queued", stopped_without_report=True),
        _state_party("k", ["r"], "waiting-ask"),
        _state_party("p", [], "waiting-permission"),
        _state_party("i", [], "idle"),
        dict(
            _state_party("pk", [], "parked"), status={"name": "parked", "label": "parked 3h", "detail": "legal answer"}
        ),
        _state_party("h", [], "idle", ctx={"pct": 80, "threshold": 70, "source": "configured", "high": True}),
    ],
    asks=[{"party": "k"}, {"party": "k"}],
)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebSidebarStateTests(unittest.TestCase):
    def _nodes(self):
        return _walk(json.loads(_render(_STATE_BOARD, "", "sidebar", "tree")), [])

    def _text(self):
        return _render(_STATE_BOARD, "", "sidebar", "text")

    def test_party_rows_carry_a_status_badge_class(self):
        classes = [node["className"] for node in self._nodes()]
        for name in ("working", "queued", "waiting-ask", "waiting-permission", "idle"):
            with self.subTest(status=name):
                self.assertIn("status-badge status-" + name, classes)

    def test_parked_row_shows_the_reason_with_a_title(self):
        details = [node for node in self._nodes() if node["className"] == "status-detail"]
        self.assertEqual([node["text"] for node in details], ["legal answer"])

    def test_ask_count_pill_only_for_parties_with_asks(self):
        pills = [node["text"] for node in self._nodes() if node["className"] == "pill ask-count"]
        self.assertEqual(pills, ["2 asks"])

    def test_stopped_without_report_pill(self):
        pills = [node for node in self._nodes() if node["className"] == "pill stopped-without-report"]
        self.assertEqual(len(pills), 1)

    def test_left_work_badge(self):
        self.assertIn("2 left", self._text())

    def test_parties_sort_by_attention_inside_a_group(self):
        text = self._text()
        self.assertLess(text.index("waiting-ask"), text.index("working"))
        self.assertLess(text.index("working"), text.index("queued"))

    def test_solo_group_puts_permission_then_context_high_before_the_rest(self):
        links = [node["text"] for node in self._nodes() if node["tag"] == "a" and node["text"] in ("p", "i", "h")]
        self.assertEqual(links, ["p", "h", "i"])

    def test_raid_header_shows_worst_member_state(self):
        header = [
            node
            for node in self._nodes()
            if node["tag"] == "h3" and "raid r" in "".join(c["text"] for c in node["children"])
        ]
        badges = [c for c in _walk(header[0], []) if c["className"].startswith("status-badge")]
        self.assertEqual([b["className"] for b in badges], ["status-badge status-waiting-ask"])


if __name__ == "__main__":
    unittest.main()
