import json
from datetime import timedelta

from guild import db, events, timeutil
from guild.commands import achievement
from tests.test_drift import DriftTestCase

_NO_DRIFT_EPIC = (
    "## T01 — First\n\n**JIRA:** DEMO-21\n**Deps:** —\n**Status:** [x] done\n\n"
    "## T02 — Second\n\n**JIRA:** DEMO-22\n**Deps:** —\n**Status:** [ ] pending\n"
)
_DRIFT_EPIC = "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n"


class QuestDoneTestCase(DriftTestCase):
    def _add_quest(self, slug, epic, tasks):
        code, out, err = self.run_cli(
            ["quest", "add", slug, "--title", "Quest " + slug, "--epic", epic, "--tasks", tasks],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _done_payload(self, slug):
        rows = self.conn.execute(
            "SELECT payload FROM events WHERE kind = 'quest.done' ORDER BY seq"
        ).fetchall()
        payloads = [json.loads(row["payload"]) for row in rows]
        return [payload for payload in payloads if payload["slug"] == slug][-1]

    def _quest_state(self, slug):
        return self.conn.execute("SELECT state FROM quests WHERE slug = ?", (slug,)).fetchone()["state"]

    def _prepare_clean_epic(self):
        self._write_epic("wave4", "jira: DEMO-20\nstatus: active\n", _NO_DRIFT_EPIC)
        self._sync_sdd()
        self._record_cards([
            self._card("DEMO-21", "done", parent_key="DEMO-20"),
            self._card("DEMO-22", "new", parent_key="DEMO-20"),
        ])
        self._add_quest("wave4-q", "wave4", "T01")
        self.run_cli(["task", "done", "wave4-q/T01", "--summary", "shipped"], "sess-1", self.repo_dir)


class DriftGateTests(QuestDoneTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave1", "status: active\n", _DRIFT_EPIC)
        self._sync_sdd()
        self._add_quest("wave1-q", "wave1", "T01")
        self._track_pr(1, "wave1-q", "T01")
        self._set_pr_lifecycle(1, "merged")

    def test_drift_refuses_done_and_lists_findings(self):
        code, out, err = self.run_cli(["quest", "done", "wave1-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("pr:acme/app#1: merged, task:wave1-q/T01 state=queued", err)
        self.assertIn("--accept-drift", err)
        self.assertEqual(self._quest_state("wave1-q"), "active")

    def test_accept_drift_records_findings_in_snapshot(self):
        code, out, err = self.run_cli(
            ["quest", "done", "wave1-q", "--accept-drift", "--force"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self._quest_state("wave1-q"), "done")
        drift = self._done_payload("wave1-q")["achievement"]["drift"]
        self.assertEqual(drift, ["pr:acme/app#1: merged, task:wave1-q/T01 state=queued"])

    def test_drift_of_other_epics_does_not_block(self):
        self._write_epic("wave2", "status: active\n", _DRIFT_EPIC)
        self._sync_sdd()
        self._add_quest("wave2-q", "wave2", "T01")
        code, out, err = self.run_cli(["quest", "done", "wave2-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_party_without_running_leader_does_not_block(self):
        self._write_epic("wave3", "status: active\n", _DRIFT_EPIC)
        self._sync_sdd()
        self._add_quest("wave3-q", "wave3", "T01")
        (self.sessions_dir / "1.json").unlink()
        code, out, err = self.run_cli(["quest", "done", "wave3-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)


class SnapshotShapeTests(QuestDoneTestCase):
    def test_epic_quest_snapshot(self):
        self._prepare_clean_epic()
        self._track_pr(7, "wave4-q", "T01")
        self._set_pr_lifecycle(7, "merged")
        code, out, err = self.run_cli(["quest", "done", "wave4-q"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        snapshot = self._done_payload("wave4-q")["achievement"]
        added = self.conn.execute("SELECT ts FROM events WHERE kind = 'quest.added'").fetchone()["ts"]
        done = self.conn.execute("SELECT ts FROM events WHERE kind = 'quest.done'").fetchone()["ts"]
        self.assertEqual(
            snapshot,
            {
                "started_at": added,
                "done_at": done,
                "party": "alpha",
                "project": "acme",
                "epic": "wave4",
                "title": "Quest wave4-q",
                "tasks_done": 1,
                "tasks_blocked_events": 0,
                "sdd_tids": ["T01"],
                "epic_progress": {"done": 1, "total": 2, "percent": 50},
                "jira_cards_done": ["DEMO-21"],
                "prs_merged": ["acme/app#7"],
                "handoffs": 0,
                "sessions": 1,
                "asks_raised": 0,
                "asks_answered": 0,
                "median_answer_seconds": None,
                "drift": [],
            },
        )

    def test_blocked_events_are_counted(self):
        self.run_cli(
            ["quest", "add", "blk-q", "--title", "Blk", "--no-epic", "--tasks", "a"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "block", "blk-q/a", "--reason", "x"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "blk-q/a", "--summary", "s"], "sess-1", self.repo_dir)
        self.run_cli(["task", "block", "blk-q/a", "--reason", "y"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "done", "blk-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(self._done_payload("blk-q")["achievement"]["tasks_blocked_events"], 2)

    def test_no_epic_quest_skips_gate_and_has_no_epic_fields(self):
        self.run_cli(
            ["quest", "add", "free-q", "--title", "Free", "--no-epic", "--tasks", "a,b"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "done", "free-q/a"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "free-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        snapshot = self._done_payload("free-q")["achievement"]
        self.assertIsNone(snapshot["epic"])
        self.assertIsNone(snapshot["epic_progress"])
        self.assertEqual(snapshot["jira_cards_done"], [])
        self.assertEqual(snapshot["sdd_tids"], ["a"])
        self.assertEqual(snapshot["tasks_done"], 1)
        self.assertEqual(snapshot["drift"], [])

    def test_epic_without_tracker_key_has_no_cards(self):
        self._write_epic("wave5", "status: active\n", _DRIFT_EPIC)
        self._sync_sdd()
        self._add_quest("wave5-q", "wave5", "T01")
        code, out, err = self.run_cli(["quest", "done", "wave5-q", "--force"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        snapshot = self._done_payload("wave5-q")["achievement"]
        self.assertEqual(snapshot["jira_cards_done"], [])
        self.assertEqual(snapshot["epic_progress"], {"done": 0, "total": 1, "percent": 0})


class LegacyEventTests(QuestDoneTestCase):
    def test_quest_done_event_without_achievement_still_applies(self):
        self.run_cli(
            ["quest", "add", "old-q", "--title", "Old", "--no-epic"], "sess-1", self.repo_dir
        )
        with db.writing(self.conn):
            events.record(
                self.conn, timeutil.utcnow(), "test@host", "alpha", None, "acme",
                "quest.done", "local", {"slug": "old-q"},
            )
        self.assertEqual(self._quest_state("old-q"), "done")


class WindowMetricTests(QuestDoneTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(
            ["quest", "add", "win-q", "--title", "Win", "--no-epic", "--tasks", "a"],
            "sess-1", self.repo_dir,
        )
        self.started = timeutil.from_iso(
            self.conn.execute("SELECT ts FROM events WHERE kind = 'quest.added'").fetchone()["ts"]
        )

    def _record(self, offset_seconds, party, kind, payload):
        with db.writing(self.conn):
            events.record(
                self.conn, self.started + timedelta(seconds=offset_seconds), "test@host",
                party, None, "acme", kind, "local", payload,
            )

    def _ask(self, ask_id, party, created_offset, answered_offset):
        self._record(
            created_offset, party, "ask.created",
            {"id": ask_id, "party": party, "question": "q", "context": "c", "refs": [], "options": []},
        )
        if answered_offset is not None:
            self._record(answered_offset, None, "ask.answered", {"id": ask_id, "answer": "a"})

    def _build(self, offset_seconds):
        return achievement.build(self.conn, "win-q", self.started + timedelta(seconds=offset_seconds), [])

    def test_handoffs_count_only_party_events_inside_window(self):
        self._record(10, "alpha", "party.handed_off", {"party": "alpha", "generation": 1, "handoff_path": "p"})
        self._record(20, "alpha", "party.handed_off", {"party": "alpha", "generation": 2, "handoff_path": "p"})
        self._record(30, "beta", "party.handed_off", {"party": "beta", "generation": 1, "handoff_path": "p"})
        self._record(500, "alpha", "party.handed_off", {"party": "alpha", "generation": 3, "handoff_path": "p"})
        self.assertEqual(self._build(100)["handoffs"], 2)

    def test_sessions_count_leader_generations_active_in_window(self):
        long_ago = timeutil.to_iso(self.started - timedelta(days=2))
        ended_before = timeutil.to_iso(self.started - timedelta(days=1))
        ended_inside = timeutil.to_iso(self.started + timedelta(seconds=40))
        starts_after = timeutil.to_iso(self.started + timedelta(seconds=900))
        self.conn.execute("DELETE FROM leaders")
        for generation, begin, end in (
            (1, long_ago, ended_before),
            (2, ended_before, ended_inside),
            (3, ended_inside, None),
            (4, starts_after, None),
        ):
            self.conn.execute(
                "INSERT INTO leaders (party, generation, session_id, session_name, started_at, ended_at)"
                " VALUES ('alpha', ?, 's', 'n', ?, ?)",
                (generation, begin, end),
            )
        self.assertEqual(self._build(100)["sessions"], 2)

    def test_ask_metrics_use_party_asks_in_window(self):
        self._ask(1, "alpha", 10, 70)
        self._ask(2, "alpha", 20, 140)
        self._ask(3, "alpha", 30, None)
        self._ask(4, "beta", 15, 25)
        self._ask(5, "alpha", 600, 700)
        snapshot = self._build(300)
        self.assertEqual(snapshot["asks_raised"], 3)
        self.assertEqual(snapshot["asks_answered"], 2)
        self.assertEqual(snapshot["median_answer_seconds"], 90.0)

    def test_no_answers_means_null_median(self):
        self._ask(1, "alpha", 10, None)
        self.assertIsNone(self._build(100)["median_answer_seconds"])

    def test_percent_rounds_down_to_whole_number(self):
        self._write_epic("wave6", "status: active\n", _DRIFT_EPIC.replace("[ ] pending", "[x] done") + (
            "\n## T02 — B\n\n**Deps:** —\n**Status:** [ ] pending\n"
            "\n## T03 — C\n\n**Deps:** —\n**Status:** [ ] pending\n"
        ))
        self._sync_sdd()
        self._add_quest("wave6-q", "wave6", "T01")
        snapshot = achievement.build(self.conn, "wave6-q", timeutil.utcnow(), [])
        self.assertEqual(snapshot["epic_progress"], {"done": 1, "total": 3, "percent": 33})
