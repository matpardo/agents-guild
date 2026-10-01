import json
from datetime import datetime, timedelta, timezone

from guild import db, paths
from guild.commands import history
from tests.testutil import GuildTestCase

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_NOW = _T0 + timedelta(days=30)


def _at(hours):
    return (_T0 + timedelta(hours=hours)).isoformat()


class HistoryTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.conn = db.connect(paths.db_path())
        self._event_count = 0

    def _event(self, hours, party, project, kind, payload):
        self._event_count += 1
        self.conn.execute(
            "INSERT INTO events (id, ts, origin, party, session_id, project, kind, visibility, payload)"
            " VALUES (?, ?, 'test@host', ?, NULL, ?, ?, 'local', ?)",
            ("evt-{}".format(self._event_count), _at(hours), party, project, kind, json.dumps(payload)),
        )
        self.conn.commit()

    def _quest_added(self, hours, slug, party, project, epic, tids):
        self._event(hours, party, project, "quest.added", {
            "slug": slug, "project": project, "party": party, "epic": epic, "title": "Quest " + slug,
            "tasks": [{"tid": tid, "title": tid} for tid in tids],
        })

    def _task_done(self, hours, slug, tid, party, project):
        self._event(hours, party, project, "task.done", {"quest": slug, "tid": tid, "summary": "s"})

    def _pr_tracked(self, hours, repo, number, party, project, quest, tid):
        self._event(hours, party, project, "pr.tracked", {
            "repo": repo, "number": number, "party": party, "task_quest": quest, "task_tid": tid,
            "what": "w", "waits": "x", "lifecycle": "open", "branch": "b", "title": "t",
            "gh_state": "OPEN", "gh_draft": False, "seeded": False,
        })

    def _pr_merged(self, hours, repo, number):
        self._event(hours, None, None, "pr.synced", {
            "repo": repo, "number": number, "lifecycle": "merged", "gh_state": "MERGED",
        })

    def _snapshot(self, slug, party, project, started, done):
        return {
            "started_at": _at(started), "done_at": _at(done), "party": party, "project": project,
            "epic": "wave4", "title": "Quest " + slug, "tasks_done": 2, "tasks_blocked_events": 1,
            "sdd_tids": ["T01", "T02"], "epic_progress": {"done": 2, "total": 4, "percent": 50},
            "jira_cards_done": ["DEMO-21"], "prs_merged": ["acme/app#1"], "handoffs": 1, "sessions": 2,
            "asks_raised": 3, "asks_answered": 2, "median_answer_seconds": 600.0, "drift": [],
        }

    def _quest_done(self, hours, slug, party, project, snapshot):
        payload = {"slug": slug}
        if snapshot is not None:
            payload["achievement"] = snapshot
        self._event(hours, party, project, "quest.done", payload)

    def _model(self, party=None, raid=None, project=None):
        return history.build_model(self.conn, _NOW, party, raid, project)


class CompletedQuestTests(HistoryTestCase):
    def test_snapshot_quest_exposes_frozen_fields(self):
        self._quest_added(0, "q1", "alpha", "acme", "wave4", ["T01", "T02"])
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        quest = self._model()["quests"][0]
        self.assertEqual(quest["slug"], "q1")
        self.assertTrue(quest["snapshot"])
        self.assertEqual(quest["party"], "alpha")
        self.assertEqual(quest["epic_progress"]["percent"], 50)
        self.assertEqual(quest["jira_cards_done"], ["DEMO-21"])
        self.assertEqual(quest["duration_seconds"], 50 * 3600)
        self.assertEqual(quest["median_answer_seconds"], 600.0)

    def test_quests_are_newest_first(self):
        for slug, done in (("old", 10), ("new", 90), ("mid", 40)):
            self._quest_done(done, slug, "alpha", "acme", self._snapshot(slug, "alpha", "acme", 0, done))
        self.assertEqual([q["slug"] for q in self._model()["quests"]], ["new", "mid", "old"])

    def test_legacy_quest_is_derived_from_events(self):
        self._quest_added(1, "legacy", "alpha", "acme", "wave4", ["T01", "T02", "T03"])
        self._task_done(2, "legacy", "T01", "alpha", "acme")
        self._task_done(3, "legacy", "T02", "alpha", "acme")
        self._event(4, "alpha", "acme", "task.blocked", {"quest": "legacy", "tid": "T03", "reason": "r"})
        self._event(5, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        self._event(500, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        self._pr_tracked(6, "acme/app", 7, "alpha", "acme", "legacy", "T01")
        self._pr_tracked(6, "acme/app", 8, "alpha", "acme", "legacy", "T02")
        self._pr_merged(7, "acme/app", 7)
        self._quest_done(30, "legacy", "alpha", "acme", None)
        quest = self._model()["quests"][0]
        self.assertFalse(quest["snapshot"])
        self.assertEqual(quest["started_at"], _at(1))
        self.assertEqual(quest["done_at"], _at(30))
        self.assertEqual(quest["duration_seconds"], 29 * 3600)
        self.assertEqual(quest["party"], "alpha")
        self.assertEqual(quest["title"], "Quest legacy")
        self.assertEqual(quest["epic"], "wave4")
        self.assertEqual(quest["tasks_done"], 2)
        self.assertEqual(quest["sdd_tids"], ["T01", "T02"])
        self.assertEqual(quest["tasks_blocked_events"], 1)
        self.assertEqual(quest["prs_merged"], ["acme/app#7"])
        self.assertEqual(quest["handoffs"], 1)
        self.assertIsNone(quest["epic_progress"])
        self.assertIsNone(quest["asks_raised"])
        self.assertEqual(quest["jira_cards_done"], [])

    def test_legacy_quest_without_added_event_has_no_duration(self):
        self._quest_done(30, "ghost", "alpha", "acme", None)
        quest = self._model()["quests"][0]
        self.assertIsNone(quest["started_at"])
        self.assertIsNone(quest["duration_seconds"])
        self.assertEqual(quest["title"], "ghost")


class FinishedRaidTests(HistoryTestCase):
    def _join(self, hours, party, raid, expires_at, lead):
        self._event(hours, party, "acme", "raid.joined", {
            "raid": raid, "party": party, "expires_at": expires_at, "lead": lead,
        })

    def _seed_ci_raid(self):
        self._join(1, "alpha", "ci", None, True)
        self._join(2, "beta", "ci", _at(100), False)
        self._event(3, "alpha", "acme", "raid.paused", {"raid": "ci", "party": "alpha"})
        self._event(4, "alpha", "acme", "raid.resumed", {"raid": "ci", "party": "alpha"})
        self._event(5, "alpha", "acme", "raid.paused", {"raid": "ci", "party": "alpha"})
        self._quest_done(10, "inside", "beta", "acme", self._snapshot("inside", "beta", "acme", 0, 10))
        self._quest_done(0.5, "before", "beta", "acme", self._snapshot("before", "beta", "acme", 0, 0.5))
        self._quest_done(11, "outsider", "gamma", "acme", self._snapshot("outsider", "gamma", "acme", 0, 11))
        self._pr_tracked(1, "acme/app", 1, "beta", "acme", None, None)
        self._pr_merged(12, "acme/app", 1)
        self._pr_tracked(1, "acme/app", 2, "gamma", "acme", None, None)
        self._pr_merged(12, "acme/app", 2)
        self._event(20, "beta", "acme", "raid.left", {"raid": "ci", "party": "beta"})
        self._event(30, "alpha", "acme", "party.closed", {"party": "alpha", "generation": 1})
        self._pr_merged(40, "acme/app", 1)

    def test_finished_raid_summary(self):
        self._seed_ci_raid()
        raids = self._model()["raids"]
        self.assertEqual([raid["name"] for raid in raids], ["ci"])
        raid = raids[0]
        self.assertEqual(raid["started_at"], _at(1))
        self.assertEqual(raid["ended_at"], _at(30))
        self.assertEqual(raid["duration_seconds"], 29 * 3600)
        self.assertEqual(
            raid["parties"], [{"party": "alpha", "lead": True}, {"party": "beta", "lead": False}]
        )
        self.assertEqual([quest["slug"] for quest in raid["quests"]], ["inside"])
        self.assertEqual(raid["prs_merged"], ["acme/app#1"])
        self.assertEqual(raid["pauses"], 2)

    def test_raid_with_active_member_is_excluded(self):
        self._join(1, "alpha", "live", None, False)
        self._join(2, "beta", "live", _at(3), False)
        self._event(4, "beta", "acme", "raid.left", {"raid": "live", "party": "beta"})
        self.assertEqual(self._model()["raids"], [])

    def test_raid_with_unexpired_member_is_excluded(self):
        self._join(1, "alpha", "live", (_NOW + timedelta(hours=1)).isoformat(), False)
        self.assertEqual(self._model()["raids"], [])

    def test_expiry_ends_raid_at_expires_at(self):
        self._join(1, "alpha", "short", _at(9), False)
        self.assertEqual(self._model()["raids"][0]["ended_at"], _at(9))

    def test_leave_after_expiry_ends_at_expiry(self):
        self._join(1, "alpha", "short", _at(9), False)
        self._event(20, "alpha", "acme", "raid.left", {"raid": "short", "party": "alpha"})
        self.assertEqual(self._model()["raids"][0]["ended_at"], _at(9))

    def test_rejoin_refreshes_membership(self):
        self._join(1, "alpha", "r", _at(3), False)
        self._join(2, "alpha", "r", _at(50), True)
        raid = self._model()["raids"][0]
        self.assertEqual(raid["ended_at"], _at(50))
        self.assertEqual(raid["parties"], [{"party": "alpha", "lead": True}])

    def test_raids_are_newest_ended_first(self):
        self._join(1, "alpha", "first", _at(5), False)
        self._join(1, "alpha", "second", _at(9), False)
        self.assertEqual([raid["name"] for raid in self._model()["raids"]], ["second", "first"])


class TotalsTests(HistoryTestCase):
    def test_totals(self):
        self._quest_done(10, "a", "alpha", "acme", self._snapshot("a", "alpha", "acme", 0, 10))
        self._quest_done(20, "b", "beta", "acme", self._snapshot("b", "beta", "acme", 0, 20))
        self._task_done(1, "a", "T01", "alpha", "acme")
        self._task_done(2, "a", "T01", "alpha", "acme")
        self._task_done(3, "b", "T01", "beta", "acme")
        self._pr_tracked(1, "acme/app", 1, "alpha", "acme", "a", "T01")
        self._pr_merged(2, "acme/app", 1)
        self._pr_merged(3, "acme/app", 1)
        self._event(1, "alpha", "acme", "ask.created", {"id": 1, "party": "alpha"})
        self._event(1, "alpha", "acme", "ask.created", {"id": 2, "party": "alpha"})
        self._event(1, "alpha", "acme", "ask.created", {"id": 3, "party": "alpha"})
        self._event(2, "alpha", None, "ask.answered", {"id": 1, "answer": "x"})
        self._event(4, "alpha", None, "ask.answered", {"id": 2, "answer": "x"})
        self._event(5, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        self._event(6, "beta", "acme", "party.handed_off", {"party": "beta"})
        self.assertEqual(self._model()["totals"], {
            "quests_done": 2,
            "prs_merged": 1,
            "tasks_done": 2,
            "asks_answered": 2,
            "median_answer_seconds": 7200.0,
            "handoffs": 2,
        })

    def test_empty_model(self):
        self.assertEqual(self._model(), {
            "quests": [], "raids": [],
            "totals": {
                "quests_done": 0, "prs_merged": 0, "tasks_done": 0, "asks_answered": 0,
                "median_answer_seconds": None, "handoffs": 0,
            },
        })


class FilterTests(HistoryTestCase):
    def setUp(self):
        super().setUp()
        self._quest_done(10, "a", "alpha", "acme", self._snapshot("a", "alpha", "acme", 0, 10))
        self._quest_done(20, "b", "beta", "other", self._snapshot("b", "beta", "other", 0, 20))
        self._event(1, "alpha", "acme", "raid.joined", {
            "raid": "ci", "party": "alpha", "expires_at": _at(2), "lead": True,
        })
        self._event(1, "beta", "other", "raid.joined", {
            "raid": "docs", "party": "beta", "expires_at": _at(3), "lead": False,
        })
        self._task_done(1, "a", "T01", "alpha", "acme")
        self._task_done(1, "b", "T01", "beta", "other")

    def test_party_filter(self):
        model = self._model(party="alpha")
        self.assertEqual([q["slug"] for q in model["quests"]], ["a"])
        self.assertEqual([r["name"] for r in model["raids"]], ["ci"])
        self.assertEqual(model["totals"]["tasks_done"], 1)

    def test_project_filter(self):
        model = self._model(project="other")
        self.assertEqual([q["slug"] for q in model["quests"]], ["b"])
        self.assertEqual([r["name"] for r in model["raids"]], ["docs"])
        self.assertEqual(model["totals"]["quests_done"], 1)

    def test_raid_filter_limits_to_member_parties(self):
        model = self._model(raid="docs")
        self.assertEqual([q["slug"] for q in model["quests"]], ["b"])
        self.assertEqual([r["name"] for r in model["raids"]], ["docs"])
        self.assertEqual(model["totals"]["tasks_done"], 1)

    def test_filters_combine(self):
        model = self._model(party="alpha", project="other")
        self.assertEqual(model["quests"], [])
        self.assertEqual(model["raids"], [])


class FormatDurationTests(GuildTestCase):
    def test_formats(self):
        self.assertEqual(history.format_duration(2 * 86400 + 3 * 3600 + 59), "2d 3h")
        self.assertEqual(history.format_duration(5 * 3600 + 10 * 60), "5h 10m")
        self.assertEqual(history.format_duration(300), "5m")
        self.assertEqual(history.format_duration(20), "<1m")
        self.assertEqual(history.format_duration(None), "unknown")


class HistoryCliTests(HistoryTestCase):
    def test_cli_renders_all_sections(self):
        self._quest_added(0, "q1", "alpha", "acme", "wave4", ["T01"])
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        self._quest_added(1, "old", "beta", "acme", None, ["T01"])
        self._quest_done(30, "old", "beta", "acme", None)
        self._event(1, "alpha", "acme", "raid.joined", {
            "raid": "ci", "party": "alpha", "expires_at": _at(9), "lead": True,
        })
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Completed quests (2)", out)
        self.assertIn("q1", out)
        self.assertIn("2d 2h", out)
        self.assertIn("50% (2/4)", out)
        self.assertIn("no snapshot", out)
        self.assertIn("Finished raids (1)", out)
        self.assertIn("alpha (lead)", out)
        self.assertIn("Totals", out)

    def test_cli_filters(self):
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        self._quest_done(60, "q2", "beta", "acme", self._snapshot("q2", "beta", "acme", 0, 60))
        code, out, err = self.run_cli(["history", "--party", "beta"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("q2", out)
        self.assertNotIn("q1", out)

    def test_cli_empty(self):
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Completed quests (0)", out)
