import json
import sqlite3
from datetime import timedelta

from guild import compact, config, db, events, paths, timeutil
from guild.cli import _build_context, build_parser
from guild.commands import project_status, rebuild, timer
from guild.errors import GuildError
from tests.testutil import GuildTestCase

_SNAPSHOT_TABLES = (
    "epics", "tasks", "cards", "prs", "pr_shared_areas", "pr_files", "resource_samples", "resource_machine",
)
_MACHINE = {
    "disk_total": 1, "disk_used": 1, "mem_total": 1, "mem_available": 1, "guild_db_bytes": 1, "docker": None,
}
_REPO = "acme/app"


def _epic_payload(status):
    return {
        "project": "acme", "epic": "e1", "sdd_path": "sdd/e1", "sdd_status": status,
        "tasks": [{"tid": "T01", "title": "First", "jira_key": None, "deps": [], "order_idx": 0, "sdd_status": status}],
    }


def _tracker_payload(status):
    return {
        "project": "acme",
        "cards": [{"key": "A-1", "status": status, "status_category": "x", "issue_type": "Task", "parent_key": None}],
    }


def _pr_synced_payload(synced_at, title):
    return {
        "repo": _REPO, "number": 7, "lifecycle": "ready", "gh_state": "OPEN", "gh_draft": 0, "branch": "feat",
        "title": title, "checks_failing": 0, "checks_passing": 1, "synced_at": synced_at,
    }


class CompactFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", [_REPO])
        self.base = timeutil.utcnow() - timedelta(days=5)
        self.tick = 0
        self.ctx = _build_context("sess-1", self.repo_dir)
        self.addCleanup(self.ctx.conn.close)

    def _record(self, kind, payload, project="acme"):
        self.tick += 1
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn, self.base + timedelta(minutes=self.tick), "tester@host", None, None, project,
                kind, "local", payload,
            )

    def _track_pr(self):
        self._record(
            "pr.tracked",
            {
                "repo": _REPO, "number": 7, "party": "alpha", "task_quest": None, "task_tid": None, "what": "w",
                "waits": "x", "lifecycle": "ready", "branch": "feat", "title": "t", "gh_state": "OPEN",
                "gh_draft": 0, "seeded": 0,
            },
        )

    def _sync_pr(self, title):
        self._record("pr.synced", _pr_synced_payload("2026-10-01T00:00:00Z{}".format(self.tick), title))

    def _set_pr(self, waits):
        self._record("pr.set", {"repo": _REPO, "number": 7, "lifecycle": "ready", "waits": waits})

    def _seqs(self, kind):
        rows = self.ctx.conn.execute("SELECT seq FROM events WHERE kind = ? ORDER BY seq", (kind,)).fetchall()
        return [row["seq"] for row in rows]

    def _snapshot(self):
        snapshot = {}
        for table in _SNAPSHOT_TABLES:
            rows = self.ctx.conn.execute("SELECT * FROM {}".format(table)).fetchall()
            snapshot[table] = sorted(json.dumps(list(row), default=str) for row in rows)
        return snapshot

    def _rebuilt_snapshot(self):
        rebuild.run(self.ctx)
        return self._snapshot()

    def _compact(self, retention_days):
        return compact.apply(self.ctx, compact.plan(self.ctx, retention_days))

    def _seed_resources(self, days_ago):
        self.tick += 1
        when = timeutil.utcnow() - timedelta(days=days_ago)
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn, when, "tester@host", None, None, "acme", "resources.sampled", "local",
                {"items": [["worktree", "/p", 5, "ok", "", ""]], "machine": _MACHINE},
            )


class CompactDedupTests(CompactFixture):
    def test_run_of_identical_epic_syncs_keeps_first_and_last(self):
        for _ in range(5):
            self._record("epic.synced", _epic_payload("open"))
        seqs = self._seqs("epic.synced")
        self._compact(None)
        self.assertEqual(self._seqs("epic.synced"), [seqs[0], seqs[-1]])

    def test_run_of_two_is_untouched(self):
        for _ in range(2):
            self._record("tracker.synced", _tracker_payload("open"))
        self._compact(None)
        self.assertEqual(len(self._seqs("tracker.synced")), 2)

    def test_differing_payloads_are_all_kept(self):
        for status in ("a", "b", "a", "b"):
            self._record("tracker.synced", _tracker_payload(status))
        self._compact(None)
        self.assertEqual(len(self._seqs("tracker.synced")), 4)

    def test_rebuild_after_compact_gives_identical_projections(self):
        self._track_pr()
        for status in ("open", "open", "open", "done", "done", "done", "done"):
            self._record("epic.synced", _epic_payload(status))
            self._record("tracker.synced", _tracker_payload(status))
        for title in ("t1", "t1", "t1", "t2", "t2", "t2"):
            self._sync_pr(title)
        self._seed_resources(1)
        before = self._rebuilt_snapshot()
        self._compact(30)
        self.assertEqual(self._rebuilt_snapshot(), before)

    def test_pr_syncs_ignore_synced_at_when_comparing(self):
        self._track_pr()
        for _ in range(4):
            self._sync_pr("same")
        seqs = self._seqs("pr.synced")
        self._compact(None)
        self.assertEqual(self._seqs("pr.synced"), [seqs[0], seqs[-1]])

    def test_pr_set_between_syncs_breaks_the_run(self):
        self._track_pr()
        self._sync_pr("same")
        self._sync_pr("same")
        self._set_pr("waits-a")
        self._sync_pr("same")
        self._sync_pr("same")
        before = self._rebuilt_snapshot()
        self._compact(None)
        self.assertEqual(len(self._seqs("pr.synced")), 4)
        self.assertEqual(self._rebuilt_snapshot(), before)

    def test_pr_activity_and_synced_at_survive_after_compact(self):
        self._track_pr()
        for _ in range(5):
            self._sync_pr("same")
        before = self._rebuilt_snapshot()
        self._compact(None)
        after = self._rebuilt_snapshot()
        self.assertEqual(after["prs"], before["prs"])

    def test_board_freshness_is_unchanged(self):
        for _ in range(6):
            self._record("epic.synced", _epic_payload("open"))
            self._record("tracker.synced", _tracker_payload("open"))
        before = project_status._age(self.ctx.conn, self.ctx.now, "acme", "epic.synced")
        beforet = project_status._age(self.ctx.conn, self.ctx.now, "acme", "tracker.synced")
        self._compact(None)
        self.assertEqual(project_status._age(self.ctx.conn, self.ctx.now, "acme", "epic.synced"), before)
        self.assertEqual(project_status._age(self.ctx.conn, self.ctx.now, "acme", "tracker.synced"), beforet)

    def test_other_projects_are_independent(self):
        self._record("tracker.synced", _tracker_payload("open"))
        other = _tracker_payload("open")
        other["project"] = "beta"
        for _ in range(4):
            self._record("tracker.synced", other, project="beta")
        self._record("tracker.synced", _tracker_payload("open"))
        self._compact(None)
        self.assertEqual(len(self._seqs("tracker.synced")), 4)


class CompactResourcesTests(CompactFixture):
    def test_without_retention_resources_are_kept_and_reason_reported(self):
        self._seed_resources(400)
        compact_plan = compact.plan(self.ctx, None)
        self.assertIn("resources kept: no resource_retention_days configured", compact.report_lines(compact_plan, True))
        self._compact(None)
        self.assertEqual(len(self._seqs("resources.sampled")), 1)
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM resource_machine").fetchone()[0], 1)

    def test_retention_deletes_old_and_keeps_recent(self):
        self._seed_resources(40)
        self._seed_resources(2)
        self._compact(30)
        self.assertEqual(len(self._seqs("resources.sampled")), 1)
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM resource_machine").fetchone()[0], 1)
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM resource_samples").fetchone()[0], 1)


class CompactApplyTests(CompactFixture):
    def test_dry_run_deletes_nothing_and_writes_no_backup(self):
        for _ in range(5):
            self._record("epic.synced", _epic_payload("open"))
        count = self.ctx.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        code, out, err = self.run_cli(["compact", "--dry-run"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("epic.synced: would delete 3 of 5", out)
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], count)
        self.assertFalse(compact.backup_path().exists())

    def test_backup_is_a_readable_copy_taken_before_deleting(self):
        for _ in range(5):
            self._record("epic.synced", _epic_payload("open"))
        total = self.ctx.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self._compact(None)
        backup = sqlite3.connect(str(compact.backup_path()))
        self.addCleanup(backup.close)
        self.assertEqual(backup.execute("SELECT COUNT(*) FROM events").fetchone()[0], total)

    def test_failing_backup_aborts_before_any_delete(self):
        for _ in range(5):
            self._record("epic.synced", _epic_payload("open"))
        compact.backup_path().mkdir()
        before = self._seqs("epic.synced")
        with self.assertRaises(GuildError):
            self._compact(None)
        self.assertEqual(self._seqs("epic.synced"), before)

    def test_cli_reports_counts_backup_and_sizes_and_records_event(self):
        for _ in range(5):
            self._record("epic.synced", _epic_payload("open"))
        code, out, err = self.run_cli(["compact"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("epic.synced: deleted 3 of 5", out)
        self.assertIn("guild.db.pre-compact", out)
        self.assertIn("db ", out)
        self.assertEqual(len(self._seqs("db.compacted")), 1)

    def test_cli_honours_global_retention(self):
        self._seed_resources(40)
        (self.config_home / "guild" / "guild.json").write_text(json.dumps({"resource_retention_days": 30}))
        code, out, err = self.run_cli(["compact", "--dry-run"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("resources older than 30d: would delete 1 events", out)

    def test_rebuild_replays_the_compacted_event(self):
        self._compact(None)
        rebuild.run(self.ctx)


class CompactConfigTests(GuildTestCase):
    def _load(self, value):
        config_file = self.root / "guild.json"
        config_file.write_text(json.dumps({"resource_retention_days": value}))
        return config.load_global(config_file)

    def test_accepts_a_positive_integer(self):
        self.assertEqual(self._load(90)["resource_retention_days"], 90)

    def test_rejects_bad_values(self):
        for value in (0, -1, "9", True, 1.5, 3651):
            with self.subTest(value=value):
                with self.assertRaises(GuildError):
                    self._load(value)

    def test_events_index_exists(self):
        conn = db.connect(paths.db_path())
        self.addCleanup(conn.close)
        names = [row["name"] for row in conn.execute("PRAGMA index_list(events)").fetchall()]
        self.assertIn("idx_events_kind_project", names)


class CompactTimerTests(GuildTestCase):
    def test_unit_renders_low_priority_compact_service(self):
        service, timer_text = timer.render_units(timer.UNITS["compact"], "/opt/bin/guild", "1d")
        self.assertIn("ExecStart=/opt/bin/guild compact\n", service)
        self.assertIn("Nice=19", service)
        self.assertIn("IOSchedulingClass=idle", service)
        self.assertIn("Unit=guild-compact.service", timer_text)

    def test_timer_command_is_registered(self):
        args = build_parser().parse_args(["compact-timer", "print", "--every", "1d"])
        self.assertEqual(args.timer_unit, "compact")
