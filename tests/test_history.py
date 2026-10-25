import json
from datetime import datetime, timedelta, timezone

from guild import db, paths, reducers
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
        self._event(
            hours,
            party,
            project,
            "quest.added",
            {
                "slug": slug,
                "project": project,
                "party": party,
                "epic": epic,
                "title": "Quest " + slug,
                "tasks": [{"tid": tid, "title": tid} for tid in tids],
            },
        )

    def _task_done(self, hours, slug, tid, party, project):
        self._event(hours, party, project, "task.done", {"quest": slug, "tid": tid, "summary": "s"})

    def _pr_tracked(self, hours, repo, number, party, project, quest, tid):
        self._event(
            hours,
            party,
            project,
            "pr.tracked",
            {
                "repo": repo,
                "number": number,
                "party": party,
                "task_quest": quest,
                "task_tid": tid,
                "what": "w",
                "waits": "x",
                "lifecycle": "open",
                "branch": "b",
                "title": "t",
                "gh_state": "OPEN",
                "gh_draft": False,
                "seeded": False,
            },
        )

    def _pr_merged(self, hours, repo, number):
        self._event(
            hours,
            None,
            None,
            "pr.synced",
            {
                "repo": repo,
                "number": number,
                "lifecycle": "merged",
                "gh_state": "MERGED",
            },
        )

    def _lifecycle_ran(self, hours, project, event_kind, status, exit_code, output_tail):
        self._event(
            hours,
            None,
            project,
            "lifecycle.ran",
            {
                "project": project,
                "event": event_kind,
                "repo": project + "/app",
                "triggers": ["manual"],
                "argv": ["true"],
                "cwd": "/tmp",
                "status": status,
                "exit_code": exit_code,
                "duration_ms": 10,
                "output_tail": output_tail,
                "reason": None,
            },
        )

    def _snapshot(self, slug, party, project, started, done):
        return {
            "started_at": _at(started),
            "done_at": _at(done),
            "party": party,
            "project": project,
            "epic": "wave4",
            "title": "Quest " + slug,
            "tasks_done": 2,
            "tasks_blocked_events": 1,
            "sdd_tids": ["T01", "T02"],
            "epic_progress": {"done": 2, "total": 4, "percent": 50},
            "jira_cards_done": ["DEMO-21"],
            "prs_merged": ["acme/app#1"],
            "handoffs": 1,
            "sessions": 2,
            "asks_raised": 3,
            "asks_answered": 2,
            "median_answer_seconds": 600.0,
            "drift": [],
        }

    def _quest_done(self, hours, slug, party, project, snapshot):
        payload = {"slug": slug}
        if snapshot is not None:
            payload["achievement"] = snapshot
        self._event(hours, party, project, "quest.done", payload)

    def _model(self, party=None, raid=None, project=None):
        return history.build_model(self.conn, _NOW, party, raid, project, paths.projects_config_dir())


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

    def test_quests_are_newest_created_first(self):
        for slug, started, done in (("old", 1, 90), ("new", 50, 60), ("mid", 20, 30)):
            self._quest_done(done, slug, "alpha", "acme", self._snapshot(slug, "alpha", "acme", started, done))
        self.assertEqual([q["slug"] for q in self._model()["quests"]], ["new", "mid", "old"])

    def test_quests_with_same_creation_are_alphabetical(self):
        for slug, done in (("zeta", 90), ("alpha-q", 10), ("mid", 40)):
            self._quest_done(done, slug, "alpha", "acme", self._snapshot(slug, "alpha", "acme", 5, done))
        self.assertEqual([q["slug"] for q in self._model()["quests"]], ["alpha-q", "mid", "zeta"])

    def test_undated_quests_go_last_alphabetically(self):
        self._quest_done(10, "zed", "alpha", "acme", None)
        self._quest_done(20, "abe", "alpha", "acme", None)
        self._quest_added(3, "dated", "alpha", "acme", None, ["T01"])
        self._quest_done(30, "dated", "alpha", "acme", None)
        self.assertEqual([q["slug"] for q in self._model()["quests"]], ["dated", "abe", "zed"])

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


class LiveHistoryTestCase(HistoryTestCase):
    def _live(self, hours, party, project, kind, payload):
        self._event(hours, party, project, kind, payload)
        reducers.apply(
            self.conn,
            {
                "kind": kind,
                "payload": payload,
                "ts": _at(hours),
                "project": project,
                "session_id": None,
            },
        )
        self.conn.commit()

    def _live_quest(self, hours, slug, party, project, epic, tids):
        self._live(
            hours,
            party,
            project,
            "quest.added",
            {
                "slug": slug,
                "project": project,
                "party": party,
                "epic": epic,
                "title": "Quest " + slug,
                "tasks": [{"tid": tid, "title": tid} for tid in tids],
            },
        )

    def _live_task(self, hours, kind, slug, tid, party, project):
        self._live(hours, party, project, kind, {"quest": slug, "tid": tid, "summary": "s", "reason": "r"})

    def _live_done(self, hours, slug, party, project):
        self._live(hours, party, project, "quest.done", {"slug": slug})


class ActiveQuestTests(LiveHistoryTestCase):
    def test_active_quest_exposes_progress(self):
        self._live_quest(10, "q1", "alpha", "acme", "wave4", ["T01", "T02", "T03", "T04", "T05"])
        self._live_task(11, "task.done", "q1", "T01", "alpha", "acme")
        self._live_task(12, "task.done", "q1", "T02", "alpha", "acme")
        self._live_task(13, "task.started", "q1", "T03", "alpha", "acme")
        self._live_task(14, "task.blocked", "q1", "T04", "alpha", "acme")
        quest = self._model()["active_quests"][0]
        self.assertEqual(quest["slug"], "q1")
        self.assertEqual(quest["party"], "alpha")
        self.assertEqual(quest["project"], "acme")
        self.assertEqual(quest["epic"], "wave4")
        self.assertEqual(quest["title"], "Quest q1")
        self.assertEqual(quest["started_at"], _at(10))
        self.assertEqual(quest["age_seconds"], int((_NOW - (_T0 + timedelta(hours=10))).total_seconds()))
        self.assertEqual(quest["tasks"], {"done": 2, "active": 1, "blocked": 1, "queued": 1, "total": 5})
        self.assertEqual(quest["percent_done"], 40)

    def test_quest_without_tasks_is_zero_percent(self):
        self._live_quest(10, "q1", "alpha", "acme", None, [])
        quest = self._model()["active_quests"][0]
        self.assertEqual(quest["tasks"]["total"], 0)
        self.assertEqual(quest["percent_done"], 0)

    def test_newest_started_first(self):
        for slug, started in (("old", 10), ("new", 90), ("mid", 40)):
            self._live_quest(started, slug, "alpha", "acme", None, ["T01"])
        self.assertEqual([q["slug"] for q in self._model()["active_quests"]], ["new", "mid", "old"])

    def test_same_start_is_alphabetical(self):
        for slug in ("zeta", "alpha-q", "mid"):
            self._live_quest(10, slug, "alpha", "acme", None, ["T01"])
        self.assertEqual([q["slug"] for q in self._model()["active_quests"]], ["alpha-q", "mid", "zeta"])

    def test_undated_active_quests_go_last_alphabetically(self):
        for slug in ("zed", "abe"):
            self.conn.execute(
                "INSERT INTO quests (slug, party, project, epic, title, state) VALUES (?, 'alpha', 'acme', NULL, 't', 'active')",
                (slug,),
            )
        self.conn.commit()
        self._live_quest(5, "dated", "alpha", "acme", None, ["T01"])
        self.assertEqual([q["slug"] for q in self._model()["active_quests"]], ["dated", "abe", "zed"])

    def test_done_quest_is_not_active(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self._live_done(20, "q1", "alpha", "acme")
        model = self._model()
        self.assertEqual(model["active_quests"], [])
        self.assertEqual(model["totals"]["quests_done"], 1)

    def test_party_close_cascade_is_not_active(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self._live(20, "alpha", "acme", "party.closed", {"party": "alpha", "generation": 1})
        self.assertEqual(self._model()["active_quests"], [])

    def test_filters(self):
        self._live_quest(10, "a", "alpha", "acme", None, ["T01"])
        self._live_quest(11, "b", "beta", "other", None, ["T01"])
        self._event(
            1,
            "beta",
            "other",
            "raid.joined",
            {
                "raid": "docs",
                "party": "beta",
                "expires_at": _at(3),
            },
        )
        self.assertEqual([q["slug"] for q in self._model(party="alpha")["active_quests"]], ["a"])
        self.assertEqual([q["slug"] for q in self._model(project="other")["active_quests"]], ["b"])
        self.assertEqual([q["slug"] for q in self._model(raid="docs")["active_quests"]], ["b"])
        self.assertEqual(self._model(party="alpha", project="other")["active_quests"], [])

    def test_totals_unchanged_by_active_quests(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self.assertEqual(self._model()["totals"]["quests_done"], 0)


class LastActivityTests(LiveHistoryTestCase):
    def test_latest_task_event_of_the_quest_wins(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01", "T02"])
        self._live_task(20, "task.started", "q1", "T01", "alpha", "acme")
        self._live_task(30, "task.done", "q1", "T01", "alpha", "acme")
        self._event(90, "alpha", "acme", "ask.created", {"id": 1, "party": "alpha"})
        self.assertEqual(self._model()["active_quests"][0]["last_activity_at"], _at(30))

    def test_pr_events_of_the_quest_count(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self._live_task(20, "task.started", "q1", "T01", "alpha", "acme")
        self._pr_tracked(40, "acme/app", 1, "alpha", "acme", "q1", "T01")
        self._pr_merged(50, "acme/app", 1)
        self.assertEqual(self._model()["active_quests"][0]["last_activity_at"], _at(50))

    def test_other_quest_events_are_ignored(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self._live_quest(11, "q2", "alpha", "acme", None, ["T01"])
        self._live_task(20, "task.started", "q1", "T01", "alpha", "acme")
        self._live_task(60, "task.started", "q2", "T01", "alpha", "acme")
        quests = {quest["slug"]: quest for quest in self._model()["active_quests"]}
        self.assertEqual(quests["q1"]["last_activity_at"], _at(20))

    def test_falls_back_to_party_events(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self._event(70, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        self._event(80, "beta", "acme", "party.handed_off", {"party": "beta"})
        self.assertEqual(self._model()["active_quests"][0]["last_activity_at"], _at(70))

    def test_falls_back_to_none_without_any_event(self):
        self.conn.execute(
            "INSERT INTO quests (slug, party, project, epic, title, state) VALUES ('x', 'alpha', 'acme', NULL, 't', 'active')"
        )
        self.conn.commit()
        self.assertIsNone(self._model()["active_quests"][0]["last_activity_at"])


class StaleHoursTests(LiveHistoryTestCase):
    def _write_project(self, data):
        projects_dir = paths.projects_config_dir()
        projects_dir.mkdir(parents=True, exist_ok=True)
        (projects_dir / "acme.json").write_text(
            json.dumps(
                dict({"name": "acme", "paths": [str(self.root) + "/*"], "github": {"repos": ["acme/app"]}}, **data)
            )
        )

    def test_is_none_without_project_config(self):
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self.assertIsNone(self._model()["active_quests"][0]["stale_hours"])

    def test_is_none_when_config_has_no_next_section(self):
        self._write_project({})
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self.assertIsNone(self._model()["active_quests"][0]["stale_hours"])

    def test_is_none_when_next_has_no_stale_hours(self):
        self._write_project({"next": {}})
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self.assertIsNone(self._model()["active_quests"][0]["stale_hours"])

    def test_uses_project_next_stale_hours(self):
        self._write_project({"next": {"stale_hours": 12}})
        self._live_quest(10, "q1", "alpha", "acme", None, ["T01"])
        self.assertEqual(self._model()["active_quests"][0]["stale_hours"], 12)

    def test_is_none_without_project(self):
        self._live_quest(10, "q1", "alpha", None, None, ["T01"])
        self.assertIsNone(self._model()["active_quests"][0]["stale_hours"])


class IncompleteQuestTests(HistoryTestCase):
    def _marked(self, hours, slug, party, project, reason):
        self._event(hours, party, project, "quest.marked_incomplete", {"slug": slug, "reason": reason})

    def _seed_marked_quest(self):
        self._quest_added(0, "q1", "alpha", "acme", "wave4", ["T01", "T02", "T03"])
        self._task_done(1, "q1", "T01", "alpha", "acme")
        self._event(2, "alpha", "acme", "task.added", {"quest": "q1", "tid": "T04", "title": "T04"})
        self._quest_done(5, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 5))
        self._marked(6, "q1", "alpha", "acme", "dropped scope")
        self._task_done(7, "q1", "T02", "alpha", "acme")

    def test_marked_quest_moves_out_of_completed(self):
        self._seed_marked_quest()
        model = self._model()
        self.assertEqual(model["quests"], [])
        self.assertEqual(model["totals"]["quests_done"], 0)
        self.assertEqual([q["slug"] for q in model["incomplete_quests"]], ["q1"])

    def test_incomplete_entry_fields(self):
        self._seed_marked_quest()
        entry = self._model()["incomplete_quests"][0]
        self.assertEqual(entry["title"], "Quest q1")
        self.assertEqual(entry["party"], "alpha")
        self.assertEqual(entry["project"], "acme")
        self.assertEqual(entry["started_at"], _at(0))
        self.assertEqual(entry["done_at"], _at(5))
        self.assertEqual(entry["marked_at"], _at(6))
        self.assertEqual(entry["reason"], "dropped scope")
        self.assertEqual(entry["tasks_not_done"], 3)
        self.assertEqual(entry["tasks_total"], 4)

    def test_quest_marked_without_done_event_still_listed(self):
        self._quest_added(0, "q1", "alpha", "acme", None, ["T01"])
        self._marked(6, "q1", "alpha", "acme", "closed with party")
        entry = self._model()["incomplete_quests"][0]
        self.assertIsNone(entry["done_at"])
        self.assertEqual(entry["tasks_not_done"], 1)

    def test_unmarked_quests_stay_completed(self):
        self._seed_marked_quest()
        self._quest_done(9, "q2", "alpha", "acme", self._snapshot("q2", "alpha", "acme", 0, 9))
        model = self._model()
        self.assertEqual([q["slug"] for q in model["quests"]], ["q2"])
        self.assertEqual(model["totals"]["quests_done"], 1)

    def test_marked_quest_is_not_listed_in_raid(self):
        self._event(
            1,
            "alpha",
            "acme",
            "raid.joined",
            {
                "raid": "ci",
                "party": "alpha",
                "expires_at": _at(100),
            },
        )
        self._quest_done(10, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 10))
        self._marked(11, "q1", "alpha", "acme", "x")
        self.assertEqual(self._model()["raids"][0]["quests"], [])

    def test_filters_apply_to_incomplete(self):
        self._quest_done(10, "a", "alpha", "acme", self._snapshot("a", "alpha", "acme", 0, 10))
        self._quest_done(11, "b", "beta", "other", self._snapshot("b", "beta", "other", 0, 11))
        self._marked(12, "a", "alpha", "acme", "x")
        self._marked(13, "b", "beta", "other", "y")
        self.assertEqual([q["slug"] for q in self._model(party="beta")["incomplete_quests"]], ["b"])
        self.assertEqual([q["slug"] for q in self._model(project="acme")["incomplete_quests"]], ["a"])

    def test_newest_created_first(self):
        for slug, started, marked in (("old", 1, 90), ("new", 50, 60), ("mid", 20, 70)):
            self._quest_done(51, slug, "alpha", "acme", self._snapshot(slug, "alpha", "acme", started, 51))
            self._marked(marked, slug, "alpha", "acme", "x")
        self.assertEqual([q["slug"] for q in self._model()["incomplete_quests"]], ["new", "mid", "old"])

    def test_same_creation_is_alphabetical(self):
        for slug in ("zeta", "alpha-q", "mid"):
            self._quest_done(51, slug, "alpha", "acme", self._snapshot(slug, "alpha", "acme", 5, 51))
            self._marked(60, slug, "alpha", "acme", "x")
        self.assertEqual([q["slug"] for q in self._model()["incomplete_quests"]], ["alpha-q", "mid", "zeta"])

    def test_undated_go_last_alphabetically(self):
        for slug in ("zed", "abe"):
            self._marked(60, slug, "alpha", "acme", "x")
        self._quest_added(3, "dated", "alpha", "acme", None, ["T01"])
        self._marked(10, "dated", "alpha", "acme", "x")
        self.assertEqual([q["slug"] for q in self._model()["incomplete_quests"]], ["dated", "abe", "zed"])


class FinishedRaidTests(HistoryTestCase):
    def _join(self, hours, party, raid, expires_at):
        self._event(
            hours,
            party,
            "acme",
            "raid.joined",
            {
                "raid": raid,
                "party": party,
                "expires_at": expires_at,
            },
        )

    def _seed_ci_raid(self):
        self._join(1, "alpha", "ci", None)
        self._join(2, "beta", "ci", _at(100))
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
        self.assertEqual(raid["parties"], ["alpha", "beta"])
        self.assertEqual([quest["slug"] for quest in raid["quests"]], ["inside"])
        self.assertEqual(raid["prs_merged"], ["acme/app#1"])
        self.assertEqual(raid["pauses"], 2)

    def test_raid_with_active_member_is_excluded(self):
        self._join(1, "alpha", "live", None)
        self._join(2, "beta", "live", _at(3))
        self._event(4, "beta", "acme", "raid.left", {"raid": "live", "party": "beta"})
        self.assertEqual(self._model()["raids"], [])

    def test_raid_with_unexpired_member_is_excluded(self):
        self._join(1, "alpha", "live", (_NOW + timedelta(hours=1)).isoformat())
        self.assertEqual(self._model()["raids"], [])

    def test_expiry_ends_raid_at_expires_at(self):
        self._join(1, "alpha", "short", _at(9))
        self.assertEqual(self._model()["raids"][0]["ended_at"], _at(9))

    def test_leave_after_expiry_ends_at_expiry(self):
        self._join(1, "alpha", "short", _at(9))
        self._event(20, "alpha", "acme", "raid.left", {"raid": "short", "party": "alpha"})
        self.assertEqual(self._model()["raids"][0]["ended_at"], _at(9))

    def test_rejoin_refreshes_membership(self):
        self._join(1, "alpha", "r", _at(3))
        self._join(2, "alpha", "r", _at(50))
        raid = self._model()["raids"][0]
        self.assertEqual(raid["ended_at"], _at(50))
        self.assertEqual(raid["parties"], ["alpha"])

    def test_raids_are_newest_created_first(self):
        self._join(1, "alpha", "first", _at(50))
        self._join(3, "alpha", "second", _at(9))
        self.assertEqual([raid["name"] for raid in self._model()["raids"]], ["second", "first"])

    def test_raids_with_same_creation_are_alphabetical(self):
        for name in ("zeta", "alpha-r", "mid"):
            self._join(1, "alpha", name, _at(5))
        self.assertEqual([raid["name"] for raid in self._model()["raids"]], ["alpha-r", "mid", "zeta"])


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
        self.assertEqual(
            self._model()["totals"],
            {
                "quests_done": 2,
                "prs_merged": 1,
                "tasks_done": 2,
                "asks_answered": 2,
                "median_answer_seconds": 7200.0,
                "handoffs": 2,
            },
        )

    def test_empty_model(self):
        empty_totals = {
            "quests_done": 0,
            "prs_merged": 0,
            "tasks_done": 0,
            "asks_answered": 0,
            "median_answer_seconds": None,
            "handoffs": 0,
        }
        self.assertEqual(
            self._model(),
            {
                "quests": [],
                "active_quests": [],
                "incomplete_quests": [],
                "raids": [],
                "lifecycle_failures": [],
                "totals": empty_totals,
                "week_totals": empty_totals,
                "since": None,
            },
        )

    def test_since_is_first_event_timestamp(self):
        self._task_done(7, "a", "T01", "alpha", "acme")
        self._event(3, "alpha", "acme", "ask.created", {"id": 1, "party": "alpha"})
        self.assertEqual(self._model()["since"], _at(3))


class WeekTotalsTests(HistoryTestCase):
    def test_week_totals_count_only_last_seven_days(self):
        recent = 24 * 25
        old = 24 * 5
        self._quest_done(recent, "a", "alpha", "acme", self._snapshot("a", "alpha", "acme", 0, recent))
        self._quest_done(old, "b", "alpha", "acme", self._snapshot("b", "alpha", "acme", 0, old))
        self._task_done(recent, "a", "T01", "alpha", "acme")
        self._task_done(old, "b", "T01", "alpha", "acme")
        self._pr_tracked(old, "acme/app", 1, "alpha", "acme", "a", "T01")
        self._pr_tracked(old, "acme/app", 2, "alpha", "acme", "a", "T02")
        self._pr_merged(old + 1, "acme/app", 1)
        self._pr_merged(recent + 1, "acme/app", 2)
        self._event(old, "alpha", "acme", "ask.created", {"id": 1, "party": "alpha"})
        self._event(old + 1, "alpha", "acme", "ask.answered", {"id": 1, "answer": "x"})
        self._event(recent, "alpha", "acme", "ask.created", {"id": 2, "party": "alpha"})
        self._event(recent + 2, "alpha", "acme", "ask.answered", {"id": 2, "answer": "x"})
        self._event(old, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        self._event(recent, "alpha", "acme", "party.handed_off", {"party": "alpha"})
        model = self._model()
        self.assertEqual(
            model["week_totals"],
            {
                "quests_done": 1,
                "prs_merged": 1,
                "tasks_done": 1,
                "asks_answered": 1,
                "median_answer_seconds": 7200.0,
                "handoffs": 1,
            },
        )
        self.assertEqual(model["totals"]["quests_done"], 2)
        self.assertEqual(model["totals"]["prs_merged"], 2)


class FilterTests(HistoryTestCase):
    def setUp(self):
        super().setUp()
        self._quest_done(10, "a", "alpha", "acme", self._snapshot("a", "alpha", "acme", 0, 10))
        self._quest_done(20, "b", "beta", "other", self._snapshot("b", "beta", "other", 0, 20))
        self._event(
            1,
            "alpha",
            "acme",
            "raid.joined",
            {
                "raid": "ci",
                "party": "alpha",
                "expires_at": _at(2),
            },
        )
        self._event(
            1,
            "beta",
            "other",
            "raid.joined",
            {
                "raid": "docs",
                "party": "beta",
                "expires_at": _at(3),
            },
        )
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


class LifecycleFailureTests(HistoryTestCase):
    def test_failed_run_is_listed_with_last_output_line(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "failed", 1, "line one\nline two\n")
        entry = self._model()["lifecycle_failures"][0]
        self.assertEqual(entry["project"], "acme")
        self.assertEqual(entry["event"], "on_pr_merged")
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["detail"], "exit 1")
        self.assertEqual(entry["last_line"], "line two")

    def test_trailing_blank_lines_are_skipped(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "timeout", None, "real line\n\n   \n")
        entry = self._model()["lifecycle_failures"][0]
        self.assertEqual(entry["last_line"], "real line")
        self.assertEqual(entry["detail"], "timeout")

    def test_empty_output_renders_as_no_output(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "error", None, "")
        entry = self._model()["lifecycle_failures"][0]
        self.assertEqual(entry["last_line"], "")
        line = history._lifecycle_failure_line(entry)
        self.assertIn("no output", line)

    def test_ok_and_skipped_are_excluded(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "ok", 0, "all good")
        self._lifecycle_ran(2, "acme", "on_pr_merged", "skipped", None, "")
        self.assertEqual(self._model()["lifecycle_failures"], [])

    def test_project_filter_narrows_to_matching_project(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "failed", 1, "a")
        self._lifecycle_ran(2, "other", "on_pr_merged", "failed", 1, "b")
        projects = [entry["project"] for entry in self._model(project="acme")["lifecycle_failures"]]
        self.assertEqual(projects, ["acme"])

    def test_party_filter_does_not_hide_lifecycle_failures(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "failed", 1, "a")
        self._lifecycle_ran(2, "other", "on_pr_merged", "failed", 1, "b")
        projects = sorted(entry["project"] for entry in self._model(party="alpha")["lifecycle_failures"])
        self.assertEqual(projects, ["acme", "other"])

    def test_newest_first(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "failed", 1, "old")
        self._lifecycle_ran(5, "acme", "on_pr_closed", "error", None, "new")
        events = [entry["event"] for entry in self._model()["lifecycle_failures"]]
        self.assertEqual(events, ["on_pr_closed", "on_pr_merged"])


class FormatDurationTests(GuildTestCase):
    def test_formats(self):
        self.assertEqual(history.format_duration(2 * 86400 + 3 * 3600 + 59), "2d 3h")
        self.assertEqual(history.format_duration(5 * 3600 + 10 * 60), "5h 10m")
        self.assertEqual(history.format_duration(300), "5m")
        self.assertEqual(history.format_duration(20), "<1m")
        self.assertEqual(history.format_duration(None), "unknown")


class HistoryCliTests(LiveHistoryTestCase):
    def test_cli_renders_all_sections(self):
        self._quest_added(0, "q1", "alpha", "acme", "wave4", ["T01"])
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        self._quest_added(1, "old", "beta", "acme", None, ["T01"])
        self._quest_done(30, "old", "beta", "acme", None)
        self._event(
            1,
            "alpha",
            "acme",
            "raid.joined",
            {
                "raid": "ci",
                "party": "alpha",
                "expires_at": _at(9),
            },
        )
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Completed quests (2)", out)
        self.assertIn("q1", out)
        self.assertIn("2d 2h", out)
        self.assertIn("50% (2/4)", out)
        self.assertIn("no snapshot", out)
        self.assertIn("Finished raids (1)", out)
        self.assertIn("parties alpha", out)
        self.assertIn("Totals", out)

    def test_cli_filters(self):
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        self._quest_done(60, "q2", "beta", "acme", self._snapshot("q2", "beta", "acme", 0, 60))
        code, out, err = self.run_cli(["history", "--party", "beta"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("q2", out)
        self.assertNotIn("q1", out)

    def test_cli_renders_in_progress_before_completed(self):
        self._live_quest(0, "wip", "alpha", "acme", None, ["T01", "T02"])
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("In progress (1)", out)
        self.assertIn("wip - Quest wip", out)
        self.assertIn("0% (0/2 done)", out)
        self.assertLess(out.index("In progress"), out.index("Completed quests"))

    def test_cli_in_progress_empty(self):
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertIn("In progress (0)", out)

    def test_cli_renders_closed_without_completing(self):
        self._quest_done(50, "q1", "alpha", "acme", self._snapshot("q1", "alpha", "acme", 0, 50))
        self._event(60, "alpha", "acme", "quest.marked_incomplete", {"slug": "q1", "reason": "dropped scope"})
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Completed quests (0)", out)
        self.assertIn("Closed without completing (1)", out)
        self.assertIn("reason: dropped scope", out)
        self.assertLess(out.index("Completed quests"), out.index("Closed without completing"))

    def test_cli_empty(self):
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Completed quests (0)", out)

    def test_cli_renders_lifecycle_failures(self):
        self._lifecycle_ran(1, "acme", "on_pr_merged", "failed", 1, "boom\n")
        code, out, err = self.run_cli(["history"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("Lifecycle failures (1)", out)
        self.assertIn("acme lifecycle.on_pr_merged failed (exit 1): boom", out)
