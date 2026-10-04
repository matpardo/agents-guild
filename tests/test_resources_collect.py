import json
import shutil
import unittest
from unittest import mock

from guild import locking, paths, probe
from guild.cli import _build_context
from guild.errors import GuildError
from guild.resources import collect
from tests import resources_fixtures as fixtures
from tests.testutil import GuildTestCase

_DEADLINE_SECONDS = 1200
_TOTALS_TEXT = (
    json.dumps({"Type": "Images", "Size": "1GB", "Reclaimable": "500MB (50%)"}) + "\n"
    + json.dumps({"Type": "Containers", "Size": "10MB", "Reclaimable": "0B"}) + "\n"
    + json.dumps({"Type": "Local Volumes", "Size": "20MB", "Reclaimable": "0B"}) + "\n"
    + json.dumps({"Type": "Build Cache", "Size": "5MB", "Reclaimable": "0B"}) + "\n"
)


def _healthy_docker(df):
    return fixtures.ok_result(json.dumps(df)), fixtures.ok_result(_TOTALS_TEXT)


def _responder(du_sizes, docker_results):
    def respond(argv):
        if argv[0] == "du":
            return fixtures.ok_result("{}\t{}\n".format(du_sizes.get(argv[-1], 1000), argv[-1]))
        if "-v" in argv:
            return docker_results[0]
        return docker_results[1]

    return respond


class CollectFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        fixtures.init_clone(self.repo_dir, "acme/app")
        self.ctx = _build_context("sess-1", self.repo_dir)

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def collect(self, runner):
        clock = fixtures.FakeClock([0])
        return collect.collect(self.ctx, runner, clock, _DEADLINE_SECONDS)

    def healthy_runner(self, du_sizes, df):
        return fixtures.FakeProbe(_responder(du_sizes, _healthy_docker(df)))

    def sampled_events(self):
        rows = self.ctx.conn.execute(
            "SELECT project, ts, payload FROM events WHERE kind = 'resources.sampled' ORDER BY seq"
        ).fetchall()
        return [(row["project"], row["ts"], json.loads(row["payload"])) for row in rows]

    def event_for(self, project):
        return [payload for name, _, payload in self.sampled_events() if name == project][0]

    def add_project(self, name, repo, clone_name):
        project_root = self.root / "projects" / name
        clone = project_root / clone_name
        fixtures.init_clone(clone, repo)
        config = {"name": name, "paths": [str(project_root) + "/*"], "github": {"repos": [repo]}}
        (self.config_home / "guild" / "projects" / "{}.json".format(name)).write_text(json.dumps(config))
        return clone


class CollectRecordTests(CollectFixture):
    def test_one_event_per_project_with_payload_shape(self):
        runner = self.healthy_runner({str(self.repo_dir): 4096}, {})
        self.collect(runner)
        events = self.sampled_events()
        self.assertEqual([name for name, _, _ in events], ["acme"])
        payload = events[0][2]
        self.assertEqual(
            payload["items"],
            [["worktree", str(self.repo_dir), 4096, "ok", "", payload["items"][0][5]]],
        )
        machine = payload["machine"]
        self.assertEqual(
            set(machine),
            {"disk_total", "disk_used", "mem_total", "mem_available", "guild_db_bytes", "docker"},
        )
        self.assertEqual(
            machine["docker"],
            {
                "images": 1000000000,
                "images_reclaimable": 500000000,
                "containers": 10000000,
                "volumes": 20000000,
                "build_cache": 5000000,
            },
        )
        self.assertGreater(machine["disk_total"], 0)

    def test_event_is_local_with_no_party_or_session(self):
        self.collect(self.healthy_runner({}, {}))
        row = self.ctx.conn.execute(
            "SELECT party, session_id, visibility FROM events WHERE kind = 'resources.sampled'"
        ).fetchone()
        self.assertEqual((row["party"], row["session_id"], row["visibility"]), (None, None, "local"))

    def test_projection_rows_are_written(self):
        self.collect(self.healthy_runner({str(self.repo_dir): 4096}, {}))
        rows = self.ctx.conn.execute("SELECT project, category, bytes FROM resource_samples").fetchall()
        self.assertEqual([(row["project"], row["category"], row["bytes"]) for row in rows], [("acme", "worktree", 4096)])
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM resource_machine").fetchone()[0], 1)

    def test_all_events_of_one_collect_share_a_timestamp(self):
        self.add_project("zeta", "zeta/svc", "svc")
        self.collect(self.healthy_runner({}, {}))
        self.assertEqual(len({ts for _, ts, _ in self.sampled_events()}), 1)

    def test_a_project_without_items_still_gets_an_event(self):
        project_root = self.root / "projects" / "empty"
        project_root.mkdir(parents=True)
        config = {"name": "empty", "paths": [str(project_root) + "/*"], "github": {"repos": ["acme/none"]}}
        (self.config_home / "guild" / "projects" / "empty.json").write_text(json.dumps(config))
        self.collect(self.healthy_runner({}, {}))
        self.assertEqual(self.event_for("empty")["items"], [])

    def test_claude_scratch_is_attributed_to_the_clone(self):
        scratch = self.claude_scratch_dir / paths.encode_cwd(self.repo_dir) / "session-1"
        fixtures.write_bytes(scratch / "note.txt", 10)
        sizes = {str(self.claude_scratch_dir / paths.encode_cwd(self.repo_dir)): 777}
        self.collect(self.healthy_runner(sizes, {}))
        items = {(row[0], row[1]): row for row in self.event_for("acme")["items"]}
        self.assertEqual(items[("claude_scratch", str(self.repo_dir))][2], 777)

    def test_docker_items_are_attributed_by_working_dir(self):
        container = {
            "ID": "a" * 64,
            "Names": "app-web-1",
            "Image": "app-web",
            "State": "running",
            "Size": "5MB",
            "Labels": "com.docker.compose.project.working_dir={},com.docker.compose.project=app".format(
                self.repo_dir
            ),
        }
        self.collect(self.healthy_runner({}, {"Containers": [container]}))
        categories = [row[0] for row in self.event_for("acme")["items"]]
        self.assertIn("docker_container", categories)
        self.assertEqual([name for name, _, _ in self.sampled_events()], ["acme"])

    def test_unattributed_docker_items_go_to_a_null_project_event(self):
        volume = {"Name": "loose_volume", "Labels": "", "Size": "1MB"}
        self.collect(self.healthy_runner({}, {"Volumes": [volume]}))
        projects = [name for name, _, _ in self.sampled_events()]
        self.assertEqual(projects, ["acme", None])
        self.assertEqual(self.event_for(None)["items"][0][:3], ["docker_volume", "loose_volume", 1000000])

    def test_items_are_sorted(self):
        self.add_project("zeta", "zeta/svc", "svc")
        volumes = [{"Name": name, "Labels": "", "Size": "1MB"} for name in ("b_vol", "a_vol")]
        self.collect(self.healthy_runner({}, {"Volumes": volumes}))
        items = self.event_for(None)["items"]
        self.assertEqual([row[1] for row in items], ["a_vol", "b_vol"])


class CollectFlagTests(CollectFixture):
    def _worktree(self, branch):
        linked = self.repo_dir / ".claude" / "worktrees" / branch
        fixtures.add_worktree(self.repo_dir, linked, branch)
        return linked

    def _pr(self, number, branch, lifecycle):
        self.ctx.conn.execute(
            "INSERT INTO prs (repo, number, party, what, lifecycle, branch, seeded) VALUES (?, ?, 'p', 'w', ?, ?, 0)",
            ("acme/app", number, lifecycle, branch),
        )

    def test_merged_and_closed_worktrees_are_flagged_at_collect_time(self):
        merged = self._worktree("feat-a")
        closed = self._worktree("feat-b")
        self._worktree("feat-c")
        self._pr(1, "feat-a", "merged")
        self._pr(2, "feat-b", "closed")
        self._pr(3, "feat-c", "ready")
        self.collect(self.healthy_runner({}, {}))
        flags = {row[1]: row[4] for row in self.event_for("acme")["items"] if row[0] == "worktree"}
        self.assertEqual(flags[str(merged.resolve())], "merged")
        self.assertEqual(flags[str(closed.resolve())], "closed")
        self.assertEqual(flags[str(self.repo_dir.resolve())], "")
        self.assertEqual(len([flag for flag in flags.values() if flag]), 2)

    def test_prunable_worktree_is_recorded_missing_with_null_bytes(self):
        linked = self._worktree("feat-gone")
        shutil.rmtree(linked)
        self.collect(self.healthy_runner({}, {}))
        rows = {row[1]: row for row in self.event_for("acme")["items"] if row[0] == "worktree"}
        row = rows[str(linked.resolve())]
        self.assertEqual((row[2], row[3]), (None, "missing"))


class CollectFailureTests(CollectFixture):
    def test_docker_unavailable_records_marker_and_null_machine_docker(self):
        denied = fixtures.failed_result(1, "", "permission denied while trying to connect")
        runner = fixtures.FakeProbe(_responder({}, (denied, denied)))
        summary = self.collect(runner)
        events = self.sampled_events()
        self.assertEqual([name for name, _, _ in events], ["acme", None])
        self.assertEqual(
            self.event_for(None)["items"], [["docker", "-", None, "unavailable", "", "permission denied"]]
        )
        for _, _, payload in events:
            self.assertIsNone(payload["machine"]["docker"])
        self.assertIn("unavailable: docker (permission denied)", summary)

    def test_docker_not_installed_still_records_worktrees(self):
        missing = fixtures.error_result("No such file or directory: 'docker'")
        runner = fixtures.FakeProbe(_responder({str(self.repo_dir): 55}, (missing, missing)))
        self.collect(runner)
        worktree = [row for row in self.event_for("acme")["items"] if row[0] == "worktree"][0]
        self.assertEqual(worktree[2], 55)
        self.assertEqual(self.event_for(None)["items"][0][5], "not installed")

    def test_raising_while_measuring_writes_nothing(self):
        def respond(argv):
            raise RuntimeError("probe exploded")

        with self.assertRaises(RuntimeError):
            self.collect(fixtures.FakeProbe(respond))
        count = self.ctx.conn.execute("SELECT COUNT(*) FROM events WHERE kind = 'resources.sampled'").fetchone()[0]
        self.assertEqual(count, 0)
        self.assertEqual(self.ctx.conn.execute("SELECT COUNT(*) FROM resource_samples").fetchone()[0], 0)

    def test_no_write_transaction_is_open_while_measuring(self):
        states = []
        inner = _responder({}, _healthy_docker({}))

        def respond(argv):
            states.append(self.ctx.conn.in_transaction)
            return inner(argv)

        self.collect(fixtures.FakeProbe(respond))
        self.assertTrue(states)
        self.assertFalse(any(states))

    def test_zero_projects_is_an_error(self):
        for config_file in (self.config_home / "guild" / "projects").glob("*.json"):
            config_file.unlink()
        with self.assertRaises(GuildError) as raised:
            self.collect(self.healthy_runner({}, {}))
        self.assertEqual(raised.exception.message, "no projects configured")
        self.assertEqual(raised.exception.exit_code, 1)

    def test_a_held_lock_prints_already_running_and_records_nothing(self):
        lock_dir = self.ctx.state_dir / "resources"
        with locking.try_lock(lock_dir, "collect.lock") as acquired:
            self.assertTrue(acquired)
            runner = self.healthy_runner({}, {})
            summary = self.collect(runner)
        self.assertEqual(summary, "collect already running")
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.sampled_events(), [])

    def test_lock_is_released_after_collect(self):
        self.collect(self.healthy_runner({}, {}))
        with locking.try_lock(self.ctx.state_dir / "resources", "collect.lock") as acquired:
            self.assertTrue(acquired)

    def test_lock_is_released_after_a_failure(self):
        def respond(argv):
            raise RuntimeError("probe exploded")

        with self.assertRaises(RuntimeError):
            self.collect(fixtures.FakeProbe(respond))
        with locking.try_lock(self.ctx.state_dir / "resources", "collect.lock") as acquired:
            self.assertTrue(acquired)


class CollectDedupeTests(CollectFixture):
    def test_shared_clone_is_measured_once_under_the_first_project(self):
        project_root = self.root / "projects" / "aaa"
        project_root.mkdir(parents=True)
        config = {"name": "aaa", "paths": [str(self.root / "projects" / "acme") + "/*"], "github": {"repos": ["acme/app"]}}
        (self.config_home / "guild" / "projects" / "aaa.json").write_text(json.dumps(config))
        runner = self.healthy_runner({}, {})
        self.collect(runner)
        du_calls = [argv for argv in runner.argvs() if argv[0] == "du" and argv[-1] == str(self.repo_dir)]
        self.assertEqual(len(du_calls), 1)
        self.assertEqual([row[0] for row in self.event_for("aaa")["items"]], ["worktree"])
        self.assertEqual(self.event_for("acme")["items"], [])


class CollectSummaryTests(CollectFixture):
    def test_summary_counts_projects_items_and_duration(self):
        self.add_project("zeta", "zeta/svc", "svc")
        summary = self.collect(self.healthy_runner({}, {}))
        self.assertEqual(summary, "sampled 2 projects, 2 items in 0s")

    def test_summary_singular_forms(self):
        summary = self.collect(self.healthy_runner({}, {}))
        self.assertEqual(summary, "sampled 1 project, 1 item in 0s")

    def test_summary_reports_duration_from_the_clock(self):
        clock = fixtures.FakeClock([100, 100, 194])
        summary = collect.collect(self.ctx, self.healthy_runner({}, {}), clock, _DEADLINE_SECONDS)
        self.assertRegex(summary, r"in 94s$")

    def test_summary_lists_unavailable_and_skipped(self):
        denied = fixtures.failed_result(1, "", "Cannot connect to the Docker daemon")
        clock = fixtures.FakeClock([0, 0, 5000])
        runner = fixtures.FakeProbe(_responder({}, (denied, denied)))
        summary = collect.collect(self.ctx, runner, clock, _DEADLINE_SECONDS)
        self.assertRegex(
            summary,
            r"^sampled 1 project, 2 items in \d+s; unavailable: docker \(daemon unreachable\); skipped: 1$",
        )

    def test_unmeasured_items_are_null_never_zero(self):
        clock = fixtures.FakeClock([0, 0, 5000])
        collect.collect(self.ctx, self.healthy_runner({}, {}), clock, _DEADLINE_SECONDS)
        row = self.event_for("acme")["items"][0]
        self.assertEqual((row[2], row[3]), (None, "skipped"))

    def test_du_unavailable_is_counted_as_unavailable_items(self):
        missing = fixtures.error_result("No such file or directory: 'du'")

        def respond(argv):
            if argv[0] == "du":
                return missing
            return _healthy_docker({})[0 if "-v" in argv else 1]

        summary = self.collect(fixtures.FakeProbe(respond))
        self.assertIn("unavailable: 1 item", summary)


class CollectCliTests(CollectFixture):
    def test_cli_collect_exits_zero_and_prints_summary(self):
        fake = fixtures.FakeProbe(_responder({}, _healthy_docker({})))
        with mock.patch.object(probe, "run_capture", fake):
            code, out, err = self.run_cli(["resources", "collect"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"^sampled 1 project, \d+ items? in \d+s")

    def test_cli_collect_with_zero_projects_exits_one(self):
        for config_file in (self.config_home / "guild" / "projects").glob("*.json"):
            config_file.unlink()
        code, out, err = self.run_cli(["resources", "collect"], None, self.root)
        self.assertEqual(code, 1)
        self.assertIn("no projects configured", err)


if __name__ == "__main__":
    unittest.main()
