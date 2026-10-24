import json
import os
import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest import mock

from guild import db, handoff_prune, locking, paths, timeutil
from guild.cli import _build_context
from tests.testutil import GuildTestCase


class PruneFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.handoffs = paths.handoffs_dir()

    def _handoff(self, session, generation):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], session, self.repo_dir)
        return self.handoffs / "alpha-g{}.md".format(generation)

    def _resume(self, session):
        self.run_cli(["party", "resume", "alpha"], session, self.repo_dir)

    def _ctx(self):
        return _build_context("sess-1", self.repo_dir)

    def _plan(self, now=None):
        ctx = self._ctx()
        if now is not None:
            ctx.now = now
        return ctx, handoff_prune.plan(ctx, self.handoffs, ctx.state_dir)

    def _sql(self, statement, params):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.execute(statement, params)
        conn.commit()
        conn.close()

    def _leader(self, generation):
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT * FROM leaders WHERE party = 'alpha' AND generation = ?", (generation,)).fetchone()
        conn.close()
        return row

    def _pruned_events(self):
        conn = db.connect(paths.db_path())
        rows = conn.execute("SELECT payload FROM events WHERE kind = 'handoff.pruned'").fetchall()
        conn.close()
        return [json.loads(row["payload"]) for row in rows]

    def _set_retention(self, days):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["handoff_retention_days"] = days
        config_file.write_text(json.dumps(data))

    def _closed_at(self):
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT MAX(ts) AS ts FROM events WHERE kind = 'party.closed'").fetchone()
        conn.close()
        return timeutil.from_iso(row["ts"])


class HandoffPruneRuleTests(PruneFixture):
    def test_latest_handoff_of_open_party_is_kept(self):
        self._handoff("sess-1", 1)
        _, plan = self._plan()
        actions = plan.actions
        kept = plan.kept_without_retention
        self.assertEqual(actions, [])
        self.assertEqual(kept, 0)

    def test_superseded_consumed_handoff_is_deleted_with_event_and_null_path(self):
        first = self._handoff("sess-1", 1)
        self._resume("sess-2")
        second = self._handoff("sess-2", 2)
        ctx, plan = self._plan()
        actions = plan.actions
        self.assertEqual([(a.verb, a.label, a.reason) for a in actions], [("delete", "alpha-g1.md", "superseded and consumed")])
        self.assertEqual(handoff_prune.apply(ctx, actions).deleted, 1)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertIsNone(self._leader(1)["handoff_path"])
        self.assertEqual([event["generation"] for event in self._pruned_events()], [1])

    def test_superseded_unconsumed_handoff_is_kept(self):
        first = self._handoff("sess-1", 1)
        self._resume("sess-2")
        self._handoff("sess-2", 2)
        self._sql("UPDATE leaders SET handoff_consumed_at = NULL WHERE generation = 1", ())
        _, plan = self._plan()
        actions = plan.actions
        self.assertEqual(actions, [])
        self.assertTrue(first.exists())

    def test_closed_party_without_retention_config_is_kept_and_counted(self):
        self._handoff("sess-1", 1)
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        _, plan = self._plan(timeutil.utcnow() + timedelta(days=4000))
        actions = plan.actions
        kept = plan.kept_without_retention
        self.assertEqual(actions, [])
        self.assertEqual(kept, 1)

    def test_closed_party_deleted_exactly_at_retention_boundary(self):
        self._handoff("sess-1", 1)
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        self._set_retention(30)
        closed_at = self._closed_at()
        _, plan = self._plan(closed_at + timedelta(days=30) - timedelta(seconds=1))
        before = plan.actions
        _, plan = self._plan(closed_at + timedelta(days=30))
        at = plan.actions
        self.assertEqual(before, [])
        self.assertEqual([(a.verb, a.reason) for a in at], [("delete", "closed party, retention 30d expired")])

    def test_party_without_project_is_kept_and_counted(self):
        self._handoff("sess-1", 1)
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        self._sql("UPDATE parties SET project = NULL WHERE name = 'alpha'", ())
        _, plan = self._plan(timeutil.utcnow() + timedelta(days=4000))
        actions = plan.actions
        kept = plan.kept_without_retention
        self.assertEqual((actions, kept), ([], 1))

    def test_unreadable_project_config_keeps_handoff_without_raising(self):
        self._handoff("sess-1", 1)
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        (self.config_home / "guild" / "projects" / "acme.json").write_text("{not json")
        _, plan = self._plan(timeutil.utcnow() + timedelta(days=4000))
        actions = plan.actions
        kept = plan.kept_without_retention
        self.assertEqual((actions, kept), ([], 1))


class HandoffPruneSafetyTests(PruneFixture):
    def _superseded_pair(self):
        first = self._handoff("sess-1", 1)
        self._resume("sess-2")
        self._handoff("sess-2", 2)
        return first

    def test_symlink_is_skipped_and_target_untouched(self):
        first = self._superseded_pair()
        target = self.root / "precious.txt"
        target.write_text("keep")
        first.unlink()
        os.symlink(str(target), str(first))
        ctx, plan = self._plan()
        actions = plan.actions
        self.assertEqual([(a.verb, a.reason) for a in actions], [("skip", "symlink")])
        self.assertEqual(handoff_prune.apply(ctx, actions).deleted, 0)
        self.assertEqual(target.read_text(), "keep")
        self.assertTrue(first.is_symlink())
        self.assertEqual(self._pruned_events(), [])

    def test_path_outside_handoffs_dir_is_skipped(self):
        self._superseded_pair()
        outside = self.root / "outside.md"
        outside.write_text("keep")
        self._sql("UPDATE leaders SET handoff_path = ? WHERE generation = 1", (str(outside),))
        ctx, plan = self._plan()
        actions = plan.actions
        self.assertEqual([(a.verb, a.reason, a.label) for a in actions], [("skip", "outside handoffs dir", str(outside))])
        handoff_prune.apply(ctx, actions)
        self.assertEqual(outside.read_text(), "keep")

    def test_missing_file_still_records_event_and_clears_path(self):
        first = self._superseded_pair()
        first.unlink()
        ctx, plan = self._plan()
        actions = plan.actions
        handoff_prune.apply(ctx, actions)
        self.assertIsNone(self._leader(1)["handoff_path"])
        self.assertEqual(len(self._pruned_events()), 1)

    def test_second_run_deletes_and_records_nothing(self):
        self._superseded_pair()
        ctx, plan = self._plan()
        actions = plan.actions
        handoff_prune.apply(ctx, actions)
        _, plan = self._plan()
        again = plan.actions
        self.assertEqual(again, [])
        self.assertEqual(len(self._pruned_events()), 1)

    def test_orphan_files_are_never_touched(self):
        self._superseded_pair()
        orphan = self.handoffs / "stray-g1.md"
        orphan.write_text("x")
        ctx, plan = self._plan()
        actions = plan.actions
        handoff_prune.apply(ctx, actions)
        self.assertTrue(orphan.exists())

    def test_report_lines_use_would_delete_in_dry_run(self):
        self._superseded_pair()
        _, plan = self._plan()
        self.assertEqual(
            handoff_prune.report_lines(plan, True),
            [
                "handoff prune (dry-run): 1 handoffs, 0 markers",
                "would delete handoff alpha-g1.md: superseded and consumed",
                "markers kept: no session registry",
            ],
        )
        plan.kept_without_retention = 2
        self.assertEqual(
            handoff_prune.report_lines(plan, False)[-1],
            "kept 2 closed-party handoff(s): no handoff_retention_days configured",
        )


class HandoffPruneRobustnessTests(PruneFixture):
    def _two_superseded(self):
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-b", self.repo_dir)
        self._handoff("sess-1", 1)
        self._resume("sess-2")
        self._handoff("sess-2", 2)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-b", self.repo_dir)
        self.run_cli(["party", "resume", "beta"], "sess-c", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-c", self.repo_dir)

    def test_malformed_close_timestamp_keeps_handoff_and_reports(self):
        self._handoff("sess-1", 1)
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        self._set_retention(30)
        self._sql("UPDATE events SET ts = 'garbage' WHERE kind = 'party.closed'", ())
        _, plan = self._plan(timeutil.utcnow() + timedelta(days=4000))
        self.assertEqual(
            [(a.verb, a.reason) for a in plan.actions], [("skip", "unreadable close timestamp")]
        )

    def test_unlink_permission_error_does_not_stop_other_entries(self):
        self._two_superseded()
        ctx, plan = self._plan()
        self.assertEqual(len(plan.actions), 2)
        real_unlink = Path.unlink

        def flaky(path, missing_ok):
            if path.name == "alpha-g1.md":
                raise PermissionError("denied")
            return real_unlink(path, missing_ok=missing_ok)

        with mock.patch.object(Path, "unlink", autospec=True, side_effect=flaky):
            result = handoff_prune.apply(ctx, plan.actions)
        self.assertEqual(result.deleted, 1)
        self.assertEqual([(a.verb, a.reason) for a in result.skipped], [("skip", "denied")])
        self.assertTrue((self.handoffs / "alpha-g1.md").exists())
        self.assertFalse((self.handoffs / "beta-g1.md").exists())
        self.assertIsNotNone(self._leader(1)["handoff_path"])
        self.assertEqual(len(self._pruned_events()), 1)

    def test_file_vanishing_between_plan_and_apply_is_not_an_error(self):
        self._two_superseded()
        ctx, plan = self._plan()
        (self.handoffs / "alpha-g1.md").unlink()
        result = handoff_prune.apply(ctx, plan.actions)
        self.assertEqual(result.deleted, 2)
        self.assertEqual(result.skipped, [])

    def test_pruned_event_carries_file_name_not_absolute_path(self):
        self._two_superseded()
        ctx, plan = self._plan()
        handoff_prune.apply(ctx, plan.actions)
        for payload in self._pruned_events():
            self.assertEqual(set(payload), {"party", "generation", "file"})
            self.assertNotIn("/", payload["file"])

    def test_held_lock_makes_prune_skip_silently(self):
        self._two_superseded()
        ctx = self._ctx()
        with locking.try_lock(ctx.state_dir / "handoff-prune", "prune.lock") as acquired:
            self.assertTrue(acquired)
            self.assertIsNone(handoff_prune.prune(ctx, self.handoffs))
        self.assertEqual(handoff_prune.prune(ctx, self.handoffs), 2)
