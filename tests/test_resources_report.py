import json
import unittest
from datetime import datetime, timedelta, timezone

from guild import db, events
from guild.cli import _build_context
from guild.errors import GuildError
from guild.resources import report
from tests.testutil import GuildTestCase

_NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
_GB = 1000000000
_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024


def _ago(**delta):
    return _NOW - timedelta(**delta)


def _machine(used, total, docker):
    return {
        "disk_total": total,
        "disk_used": used,
        "mem_total": 31 * _GB,
        "mem_available": 9 * _GB,
        "guild_db_bytes": 173000000,
        "docker": docker,
    }


_DOCKER = {
    "images": 8 * _GB,
    "images_reclaimable": 5200000000,
    "containers": 100000000,
    "volumes": 4 * _GB,
    "build_cache": 5300000000,
}


class ReportFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.ctx = _build_context("sess-1", self.repo_dir)

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def sample(self, project, when, items, machine):
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn,
                when,
                self.ctx.origin,
                None,
                None,
                project,
                "resources.sampled",
                "local",
                {"items": items, "machine": machine},
            )

    def model(self, project, since):
        return report.build_model(self.ctx.conn, _NOW, project, since, self.ctx.projects_dir)

    def project_model(self, since):
        return self.model(None, since)["projects"][0]

    def item(self, model, category, item):
        return [entry for entry in model["items"] if entry["category"] == category and entry["item"] == item][0]


def _row(category, item, size, state, flag, detail):
    return [category, item, size, state, flag, detail]


_PLAIN_MACHINE = _machine(400 * _GB, 500 * _GB, None)


class BaselineTests(ReportFixture):
    def test_baseline_is_the_latest_sample_at_or_before_the_cutoff(self):
        for when, size in ((_ago(days=3), 1), (_ago(hours=25), 2), (_ago(hours=1), 3)):
            self.sample("acme", when, [_row("worktree", "/home/u/a", size * _GB, "ok", "", "main")], _PLAIN_MACHINE)
        model = self.project_model("1d")
        self.assertEqual(model["baseline_at"], _ago(hours=25).isoformat())
        self.assertFalse(model["baseline_oldest"])
        self.assertEqual(model["sampled_at"], _ago(hours=1).isoformat())
        self.assertEqual(model["delta_bytes"], 1 * _GB)

    def test_oldest_sample_is_used_when_none_is_old_enough(self):
        for when, size in ((_ago(hours=5), 1), (_ago(hours=1), 3)):
            self.sample("acme", when, [_row("worktree", "/home/u/a", size * _GB, "ok", "", "main")], _PLAIN_MACHINE)
        model = self.project_model("1d")
        self.assertEqual(model["baseline_at"], _ago(hours=5).isoformat())
        self.assertTrue(model["baseline_oldest"])
        self.assertEqual(model["delta_bytes"], 2 * _GB)

    def test_a_single_sample_has_no_baseline_and_no_deltas(self):
        self.sample("acme", _ago(hours=1), [_row("worktree", "/home/u/a", _GB, "ok", "", "main")], _PLAIN_MACHINE)
        model = self.project_model("1d")
        self.assertIsNone(model["baseline_at"])
        self.assertIsNone(model["delta_bytes"])
        entry = self.item(model, "worktree", "/home/u/a")
        self.assertIsNone(entry["delta_bytes"])
        self.assertFalse(entry["new"])
        self.assertEqual(model["growers"], [])

    def test_a_sample_older_than_the_window_is_its_own_baseline_and_yields_no_deltas(self):
        self.sample("acme", _ago(days=3), [_row("worktree", "/home/u/a", _GB, "ok", "", "main")], _PLAIN_MACHINE)
        self.assertIsNone(self.project_model("1d")["baseline_at"])


class DeltaTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.sample(
            "acme",
            _ago(days=2),
            [
                _row("worktree", "/home/u/a", 4 * _GB, "ok", "", "main"),
                _row("worktree", "/home/u/a/w1", 2 * _GB, "ok", "", "feat-x"),
                _row("worktree", "/home/u/a/w-gone", 1 * _GB, "ok", "", "old"),
                _row("docker_image", "acme-web:latest", None, "unavailable", "", ""),
                _row("claude_scratch", "/home/u/a", 100 * _MIB, "ok", "", ""),
            ],
            _PLAIN_MACHINE,
        )
        self.sample(
            "acme",
            _ago(hours=1),
            [
                _row("worktree", "/home/u/a", 4 * _GB + 300 * _MIB, "ok", "", "main"),
                _row("worktree", "/home/u/a/w1", 5 * _GB, "ok", "merged", "feat-x"),
                _row("docker_image", "acme-web:latest", 2 * _GB, "ok", "orphaned", ""),
                _row("docker_image", "acme-new:latest", 3 * _GB, "ok", "", ""),
                _row("claude_scratch", "/home/u/a", 100 * _MIB, "ok", "", ""),
            ],
            _PLAIN_MACHINE,
        )
        self.model_under_test = self.project_model("1d")

    def test_item_delta_is_now_minus_baseline(self):
        entry = self.item(self.model_under_test, "worktree", "/home/u/a/w1")
        self.assertEqual((entry["bytes"], entry["delta_bytes"], entry["new"]), (5 * _GB, 3 * _GB, False))
        self.assertEqual((entry["flag"], entry["detail"]), ("merged", "feat-x"))

    def test_item_unmeasured_at_baseline_has_null_delta_and_is_not_new(self):
        entry = self.item(self.model_under_test, "docker_image", "acme-web:latest")
        self.assertEqual((entry["bytes"], entry["delta_bytes"], entry["new"]), (2 * _GB, None, False))

    def test_item_absent_at_baseline_is_new(self):
        entry = self.item(self.model_under_test, "docker_image", "acme-new:latest")
        self.assertEqual((entry["delta_bytes"], entry["new"]), (None, True))

    def test_category_total_and_delta_include_new_and_gone_but_not_unmeasured(self):
        categories = {entry["category"]: entry for entry in self.model_under_test["categories"]}
        worktree = categories["worktree"]
        self.assertEqual(worktree["bytes"], 9 * _GB + 300 * _MIB)
        self.assertEqual(worktree["delta_bytes"], 300 * _MIB + 3 * _GB - 1 * _GB)
        image = categories["docker_image"]
        self.assertEqual(image["bytes"], 5 * _GB)
        self.assertEqual(image["delta_bytes"], 3 * _GB)
        self.assertEqual(image["state"], "ok")

    def test_project_total_and_delta_sum_the_categories(self):
        model = self.model_under_test
        self.assertEqual(model["total_bytes"], 9 * _GB + 300 * _MIB + 5 * _GB + 100 * _MIB)
        self.assertEqual(model["delta_bytes"], (300 * _MIB + 2 * _GB) + 3 * _GB + 0)

    def test_growers_are_over_the_noise_floor_largest_first_and_include_new_items(self):
        growers = self.model_under_test["growers"]
        self.assertEqual(
            [(entry["category"], entry["item"]) for entry in growers],
            [
                ("docker_image", "acme-new:latest"),
                ("worktree", "/home/u/a/w1"),
                ("worktree", "/home/u/a"),
            ],
        )
        self.assertEqual([entry["delta_bytes"] for entry in growers], [3 * _GB, 3 * _GB, 300 * _MIB])

    def test_unchanged_items_are_not_growers(self):
        names = [entry["item"] for entry in self.model_under_test["growers"]]
        self.assertNotIn("/home/u/a/w-gone", names)

    def test_only_the_five_biggest_growers_are_kept(self):
        items_before = [_row("worktree", "/home/u/many/{}".format(index), _GB, "ok", "", "b") for index in range(8)]
        items_after = [
            _row("worktree", "/home/u/many/{}".format(index), _GB + (index + 2) * _MIB, "ok", "", "b")
            for index in range(8)
        ]
        self.sample("beta", _ago(days=2), items_before, _PLAIN_MACHINE)
        self.sample("beta", _ago(hours=1), items_after, _PLAIN_MACHINE)
        model = self.model("beta", "1d")["projects"][0]
        self.assertEqual(len(model["growers"]), 5)
        self.assertEqual(model["growers"][0]["item"], "/home/u/many/7")

    def test_growth_under_one_mebibyte_is_noise(self):
        self.sample("gamma", _ago(days=2), [_row("worktree", "/home/u/g", _GB, "ok", "", "b")], _PLAIN_MACHINE)
        self.sample("gamma", _ago(hours=1), [_row("worktree", "/home/u/g", _GB + _MIB - 1, "ok", "", "b")], _PLAIN_MACHINE)
        self.assertEqual(self.model("gamma", "1d")["projects"][0]["growers"], [])


class NullHandlingTests(ReportFixture):
    def test_unmeasured_now_is_null_everywhere_and_never_zero(self):
        self.sample("acme", _ago(days=2), [_row("worktree", "/home/u/a", _GB, "ok", "", "main")], _PLAIN_MACHINE)
        self.sample("acme", _ago(hours=1), [_row("worktree", "/home/u/a", None, "skipped", "", "main")], _PLAIN_MACHINE)
        model = self.project_model("1d")
        entry = self.item(model, "worktree", "/home/u/a")
        self.assertEqual((entry["bytes"], entry["delta_bytes"], entry["state"]), (None, None, "skipped"))
        category = model["categories"][0]
        self.assertEqual((category["bytes"], category["delta_bytes"], category["state"]), (None, None, "skipped"))
        self.assertIsNone(model["total_bytes"])
        self.assertIsNone(model["delta_bytes"])

    def test_docker_marker_is_a_category_with_state_and_detail_not_an_item(self):
        self.sample(
            None,
            _ago(hours=1),
            [_row("docker", "-", None, "unavailable", "", "permission denied")],
            _PLAIN_MACHINE,
        )
        model = self.model(None, "1d")["unattributed"]
        self.assertEqual(model["items"], [])
        self.assertEqual(
            model["categories"],
            [
                {
                    "category": "docker",
                    "bytes": None,
                    "delta_bytes": None,
                    "state": "unavailable",
                    "detail": "permission denied",
                }
            ],
        )


class MachineTests(ReportFixture):
    def _two_samples(self, before_used, after_used, items_before, items_after):
        self.sample("acme", _ago(days=2), items_before, _machine(before_used, 500 * _GB, _DOCKER))
        self.sample("acme", _ago(hours=1), items_after, _machine(after_used, 500 * _GB, _DOCKER))

    def test_machine_fields_and_disk_delta(self):
        self._two_samples(400 * _GB, 406 * _GB, [], [])
        machine = self.model(None, "1d")["machine"]
        self.assertEqual(machine["sampled_at"], _ago(hours=1).isoformat())
        self.assertEqual((machine["disk_total"], machine["disk_used"]), (500 * _GB, 406 * _GB))
        self.assertEqual(machine["disk_percent"], 81)
        self.assertEqual(machine["disk_delta"], 6 * _GB)
        self.assertEqual((machine["mem_total"], machine["mem_available"]), (31 * _GB, 9 * _GB))
        self.assertEqual(machine["guild_db_bytes"], 173000000)
        self.assertEqual(machine["docker"]["images"], 8 * _GB)
        self.assertEqual(machine["docker"]["total"], 8 * _GB + 100000000 + 4 * _GB + 5300000000)

    def test_machine_docker_is_null_when_unavailable(self):
        self.sample("acme", _ago(hours=1), [], _PLAIN_MACHINE)
        self.assertIsNone(self.model(None, "1d")["machine"]["docker"])

    def test_untracked_growth_is_machine_delta_minus_tracked_when_over_a_gibibyte(self):
        before = [_row("worktree", "/home/u/a", 10 * _GB, "ok", "", "main")]
        after = [_row("worktree", "/home/u/a", 13 * _GB, "ok", "", "main")]
        self._two_samples(400 * _GB, 406 * _GB, before, after)
        self.assertEqual(self.model(None, "1d")["machine"]["untracked_growth"], 3 * _GB)

    def test_untracked_growth_is_null_below_a_gibibyte(self):
        before = [_row("worktree", "/home/u/a", 10 * _GB, "ok", "", "main")]
        after = [_row("worktree", "/home/u/a", 15 * _GB, "ok", "", "main")]
        self._two_samples(400 * _GB, 400 * _GB + 5 * _GB + _GIB // 2, before, after)
        self.assertIsNone(self.model(None, "1d")["machine"]["untracked_growth"])

    def test_untracked_growth_counts_unattributed_deltas_as_tracked(self):
        self.sample("acme", _ago(days=2), [], _machine(400 * _GB, 500 * _GB, None))
        self.sample("acme", _ago(hours=1), [], _machine(406 * _GB, 500 * _GB, None))
        self.sample(None, _ago(days=2), [_row("docker_volume", "v", 1 * _GB, "ok", "", "")], _machine(400 * _GB, 500 * _GB, None))
        self.sample(None, _ago(hours=1), [_row("docker_volume", "v", 7 * _GB, "ok", "", "")], _machine(406 * _GB, 500 * _GB, None))
        self.assertIsNone(self.model(None, "1d")["machine"]["untracked_growth"])

    def test_untracked_growth_is_null_without_any_tracked_delta(self):
        self.sample("acme", _ago(hours=1), [], _machine(406 * _GB, 500 * _GB, None))
        self.assertIsNone(self.model(None, "1d")["machine"]["untracked_growth"])

    def test_machine_memory_nulls_are_preserved(self):
        machine = _machine(400 * _GB, 500 * _GB, None)
        machine["mem_total"] = None
        machine["mem_available"] = None
        self.sample("acme", _ago(hours=1), [], machine)
        result = self.model(None, "1d")["machine"]
        self.assertEqual((result["mem_total"], result["mem_available"]), (None, None))


class ScopeTests(ReportFixture):
    def setUp(self):
        super().setUp()
        for project in ("acme", "zeta", None):
            self.sample(
                project, _ago(hours=1), [_row("worktree", "/home/u/{}".format(project), _GB, "ok", "", "b")], _PLAIN_MACHINE
            )

    def test_projects_are_sorted_and_unattributed_is_separate(self):
        model = self.model(None, "1d")
        self.assertEqual([entry["name"] for entry in model["projects"]], ["acme", "zeta"])
        self.assertIsNotNone(model["unattributed"])
        self.assertNotIn("name", model["unattributed"])

    def test_project_filter_keeps_only_that_project(self):
        model = self.model("zeta", "1d")
        self.assertEqual([entry["name"] for entry in model["projects"]], ["zeta"])
        self.assertIsNone(model["unattributed"])

    def test_unknown_project_is_an_error(self):
        with self.assertRaises(GuildError) as raised:
            self.model("nope", "1d")
        self.assertIn("unknown project 'nope'", raised.exception.message)
        self.assertEqual(raised.exception.exit_code, 1)

    def test_configured_project_without_samples_is_known_and_empty(self):
        model = self.model("acme", "1d")
        self.assertEqual(len(model["projects"]), 1)

    def test_invalid_since_is_an_error(self):
        with self.assertRaises(GuildError):
            self.model(None, "soon")

    def test_no_samples_gives_an_empty_model(self):
        self.ctx.conn.execute("DELETE FROM resource_samples")
        self.ctx.conn.execute("DELETE FROM resource_machine")
        model = self.model(None, "1d")
        self.assertEqual((model["projects"], model["unattributed"], model["machine"]), ([], None, None))

    def test_model_is_json_serializable_and_carries_since_and_generated_at(self):
        model = self.model(None, "3d")
        json.dumps(model)
        self.assertEqual(model["since"], "3d")
        self.assertEqual(model["generated_at"], _NOW.isoformat())


class RenderTests(ReportFixture):
    def _seed_example(self):
        before = [
            _row("worktree", "/home/u/acme/app", 3800000000, "ok", "", "main"),
            _row("worktree", "/home/u/acme/app/.claude/worktrees/feat-x", 1400000000, "ok", "", "feat-x"),
            _row("docker_image", "acme-feat-x-web:latest", 100000000, "ok", "", ""),
        ]
        after = [
            _row("worktree", "/home/u/acme/app", 4100000000, "ok", "", "main"),
            _row("worktree", "/home/u/acme/app/.claude/worktrees/feat-x", 3200000000, "ok", "merged", "feat-x"),
            _row("docker_image", "acme-feat-x-web:latest", 2300000000, "ok", "orphaned", ""),
            _row("claude_scratch", "/home/u/acme/app", 100000000, "ok", "", ""),
        ]
        self.sample("acme", _ago(days=2), before, _machine(406 * _GB, 500 * _GB, _DOCKER))
        self.sample("acme", _ago(minutes=41), after, _machine(412 * _GB, 500 * _GB, _DOCKER))
        self.sample(
            None,
            _ago(days=2),
            [_row("docker_image", "5e6f7a8b9c0d", 1200000000, "ok", "dangling", "")],
            _machine(406 * _GB, 500 * _GB, _DOCKER),
        )
        self.sample(
            None,
            _ago(minutes=41),
            [_row("docker_image", "5e6f7a8b9c0d", 1400000000, "ok", "dangling", "")],
            _machine(412 * _GB, 500 * _GB, _DOCKER),
        )

    def _lines(self, project, since):
        return report.render(self.model(project, since), _NOW)

    def test_golden_render(self):
        self._seed_example()
        baseline = _ago(days=2).astimezone().strftime("%Y-%m-%d %H:%M")
        expected = [
            "machine   disk 82% used (412.0 GB of 500.0 GB, +6.0 GB in 1d)   ram 9.0 GB available of 31.0 GB",
            "          docker 17.4 GB (reclaimable 5.2 GB)   guild.db 173 MB   sampled 41m ago",
            "untracked growth: +1.4 GB (machine +6.0 GB, tracked +4.6 GB)",
            "",
            "acme   total 9.7 GB (+4.4 GB)   baseline {} (sampled 41m ago)".format(baseline),
            "  worktree          7.3 GB (+2.1 GB)",
            "    /home/u/acme/app                            4.1 GB   +300 MB",
            "    /home/u/acme/app/.claude/worktrees/feat-x   3.2 GB   +1.8 GB   merged, still on disk",
            "  docker_image      2.3 GB (+2.2 GB)",
            "    acme-feat-x-web:latest                      2.3 GB   +2.2 GB   orphaned",
            "  claude_scratch    100 MB (+100 MB)",
            "    /home/u/acme/app                            100 MB   new",
            "  top growers: acme-feat-x-web:latest +2.2 GB, feat-x +1.8 GB, app +300 MB, app +100 MB",
            "",
            "unattributed   total 1.4 GB (+200 MB)   baseline {} (sampled 41m ago)".format(baseline),
            "  docker_image      1.4 GB (+200 MB)",
            "    5e6f7a8b9c0d   1.4 GB   +200 MB   dangling",
            "  top growers: 5e6f7a8b9c0d +200 MB",
        ]
        self.assertEqual(self._lines(None, "1d"), expected)

    def test_oldest_available_baseline_is_labeled(self):
        for when, size in ((_ago(hours=5), 1), (_ago(hours=1), 3)):
            self.sample("acme", when, [_row("worktree", "/home/u/acme/app", size * _GB, "ok", "", "main")], _PLAIN_MACHINE)
        header = [line for line in self._lines(None, "1d") if line.startswith("acme")][0]
        self.assertIn("(oldest available)", header)

    def test_no_samples_message(self):
        self.assertEqual(self._lines(None, "1d"), ["no samples yet; run guild resources collect"])

    def test_single_sample_says_no_earlier_sample_and_shows_no_deltas(self):
        self.sample("acme", _ago(hours=1), [_row("worktree", "/home/u/acme/app", 4100000000, "ok", "", "main")], _PLAIN_MACHINE)
        lines = self._lines(None, "1d")
        header = [line for line in lines if line.startswith("acme")][0]
        self.assertIn("no earlier sample", header)
        self.assertNotIn("+", "".join(lines[lines.index(header):]))

    def test_unmeasured_items_render_a_question_mark(self):
        self.sample("acme", _ago(days=2), [_row("worktree", "/home/u/acme/app", _GB, "ok", "", "main")], _PLAIN_MACHINE)
        self.sample("acme", _ago(hours=1), [_row("worktree", "/home/u/acme/app", None, "skipped", "", "main")], _PLAIN_MACHINE)
        lines = self._lines(None, "1d")
        item_line = [line for line in lines if line.startswith("    /home/u/acme/app")][0]
        self.assertRegex(item_line, r"\?\s+\?")

    def test_docker_marker_renders_as_unavailable_category(self):
        self.sample(None, _ago(hours=1), [_row("docker", "-", None, "unavailable", "", "permission denied")], _PLAIN_MACHINE)
        lines = self._lines(None, "1d")
        self.assertIn("  docker            unavailable (permission denied)", lines)

    def test_machine_line_without_docker_or_memory(self):
        machine = _machine(400 * _GB, 500 * _GB, None)
        machine["mem_total"] = None
        machine["mem_available"] = None
        self.sample("acme", _ago(hours=1), [], machine)
        lines = self._lines(None, "1d")
        self.assertIn("ram n/a", lines[0])
        self.assertIn("docker n/a", lines[1])

    def test_categories_show_top_ten_items_and_a_remainder(self):
        items = [_row("worktree", "/home/u/many/{:02d}".format(index), (index + 1) * _GB, "ok", "", "b") for index in range(13)]
        self.sample("acme", _ago(hours=1), items, _PLAIN_MACHINE)
        lines = self._lines(None, "1d")
        shown = [line for line in lines if line.startswith("    /home/u/many/")]
        self.assertEqual(len(shown), 10)
        self.assertIn("/home/u/many/12", shown[0])
        self.assertIn("    (+3 more)", lines)

    def test_flag_labels_cover_every_flag(self):
        self.assertEqual(
            set(report._FLAG_LABELS),
            {"merged", "closed", "orphaned", "dangling", "unused"},
        )
        self.assertEqual(report._FLAG_LABELS["merged"], "merged, still on disk")
        self.assertEqual(report._FLAG_LABELS["closed"], "closed, still on disk")

    def test_categories_include_docker_marker(self):
        self.assertEqual(
            report._CATEGORIES,
            (
                "worktree",
                "docker_container",
                "docker_image",
                "docker_volume",
                "claude_scratch",
                "claude_transcripts",
                "docker",
            ),
        )


if __name__ == "__main__":
    unittest.main()
