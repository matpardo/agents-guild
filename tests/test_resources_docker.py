import json
import unittest
from pathlib import Path

from guild.resources import docker
from tests import resources_fixtures as fixtures

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "docker"
_DF_VERBOSE_ARGV = ["docker", "system", "df", "-v", "--format", "json"]
_DF_ARGV = ["docker", "system", "df", "--format", "json"]
_WORKTREES = "/home/u/acme/app/.claude/worktrees/"
_EXISTING = {
    "/home/u/acme/app",
    _WORKTREES + "feat-x",
    _WORKTREES + "feat-y",
    "/home/u/zeta/svc",
}
_ROOTS = {
    "acme": ["/home/u/acme", "/home/u/acme/app", _WORKTREES + "feat-x", _WORKTREES + "feat-y"],
    "zeta": ["/home/u/zeta", "/home/u/zeta/svc"],
}
_CHECKOUTS = {
    "acme": ["/home/u/acme/app", _WORKTREES + "feat-x", _WORKTREES + "feat-y"],
    "zeta": ["/home/u/zeta/svc"],
}


def _fixture_text(name):
    return (_FIXTURES / name).read_text()


def _fixture_df():
    return json.loads(_fixture_text("system_df_v.json"))


def _responder(verbose, totals):
    def respond(argv):
        if argv == _DF_VERBOSE_ARGV:
            return verbose
        return totals

    return respond


def _healthy_probe():
    return fixtures.FakeProbe(
        _responder(
            fixtures.ok_result(_fixture_text("system_df_v.json")),
            fixtures.ok_result(_fixture_text("system_df.jsonl")),
        )
    )


def _attribute(df):
    return docker.attribute(df, _ROOTS, _CHECKOUTS, lambda path: path in _EXISTING)


def _rows_by_item(rows):
    return {(row[0], row[1]): row for row in rows}


class ScanTests(unittest.TestCase):
    def test_healthy_scan_runs_the_two_calls_with_a_sixty_second_timeout(self):
        runner = _healthy_probe()
        result = docker.scan(runner)
        self.assertTrue(result["ok"])
        self.assertEqual(runner.argvs(), [_DF_VERBOSE_ARGV, _DF_ARGV])
        self.assertEqual([call["timeout_seconds"] for call in runner.calls], [60, 60])
        self.assertEqual(len(result["df"]["Images"]), 7)

    def test_totals_are_parsed_in_bytes(self):
        totals = docker.scan(_healthy_probe())["totals"]
        self.assertEqual(
            totals,
            {
                "images": 7779000000,
                "images_reclaimable": 2341000000,
                "containers": 189600000,
                "volumes": 7342000000,
                "build_cache": 7512000000,
            },
        )

    def _failure(self, verbose, totals):
        result = docker.scan(fixtures.FakeProbe(_responder(verbose, totals)))
        self.assertFalse(result["ok"])
        return result["reason"]

    def test_missing_binary_is_not_installed(self):
        error = fixtures.error_result("No such file or directory: 'docker'")
        self.assertEqual(self._failure(error, error), "not installed")

    def test_permission_denied(self):
        denied = fixtures.failed_result(
            1, "", "permission denied while trying to connect to the docker API at unix:///var/run/docker.sock"
        )
        self.assertEqual(self._failure(denied, denied), "permission denied")

    def test_daemon_unreachable(self):
        unreachable = fixtures.failed_result(
            1, "", "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
        )
        self.assertEqual(self._failure(unreachable, unreachable), "daemon unreachable")

    def test_timeout(self):
        self.assertEqual(self._failure(fixtures.timeout_result(), fixtures.timeout_result()), "timeout")

    def test_unparseable_verbose_output(self):
        totals = fixtures.ok_result(_fixture_text("system_df.jsonl"))
        self.assertEqual(self._failure(fixtures.ok_result("not json"), totals), "unparseable")

    def test_verbose_output_that_is_not_an_object_is_unparseable(self):
        totals = fixtures.ok_result(_fixture_text("system_df.jsonl"))
        self.assertEqual(self._failure(fixtures.ok_result("[1, 2]"), totals), "unparseable")

    def test_unparseable_totals_output(self):
        verbose = fixtures.ok_result(_fixture_text("system_df_v.json"))
        self.assertEqual(self._failure(verbose, fixtures.ok_result("nope\n")), "unparseable")

    def test_other_non_zero_exit_is_unparseable(self):
        broken = fixtures.failed_result(125, "", "something else broke")
        self.assertEqual(self._failure(broken, broken), "unparseable")

    def test_failure_of_the_second_call_is_reported(self):
        verbose = fixtures.ok_result(_fixture_text("system_df_v.json"))
        self.assertEqual(self._failure(verbose, fixtures.timeout_result()), "timeout")

    def test_totals_tolerate_missing_types(self):
        verbose = fixtures.ok_result(_fixture_text("system_df_v.json"))
        only_images = fixtures.ok_result(json.dumps({"Type": "Images", "Size": "1GB", "Reclaimable": "0B (0%)"}) + "\n")
        result = docker.scan(fixtures.FakeProbe(_responder(verbose, only_images)))
        self.assertEqual(result["totals"]["images"], 1000000000)
        self.assertIsNone(result["totals"]["build_cache"])
        self.assertIsNone(result["totals"]["containers"])


class ComposeLabelTests(unittest.TestCase):
    def test_project_and_working_dir_are_read_even_when_config_files_hold_commas(self):
        label = (
            "com.docker.compose.project.config_files=/a/docker-compose.yml,/a/docker-compose.override.yml,"
            "com.docker.compose.project.working_dir=/a,com.docker.compose.project=feat-x,"
            "com.docker.compose.service=web"
        )
        self.assertEqual(docker.compose_project(label), "feat-x")
        self.assertEqual(docker.compose_working_dir(label), "/a")

    def test_project_key_does_not_match_the_working_dir_key(self):
        label = "com.docker.compose.project.working_dir=/a"
        self.assertIsNone(docker.compose_project(label))

    def test_missing_labels_are_none(self):
        for label in ("", None, "other=1"):
            with self.subTest(label=label):
                self.assertIsNone(docker.compose_project(label))
                self.assertIsNone(docker.compose_working_dir(label))


class AttributeContainerTests(unittest.TestCase):
    def setUp(self):
        self.result = _attribute(_fixture_df())

    def _row(self, project, category, item):
        return _rows_by_item(self.result[project])[(category, item)]

    def test_labeled_container_goes_to_the_owner_of_its_working_dir(self):
        row = self._row("acme", "docker_container", "feat-x-web-1")
        self.assertEqual(row, ["docker_container", "feat-x-web-1", 21700000, "ok", "", "feat-x"])

    def test_virtual_suffix_is_ignored_and_tiny_sizes_parse(self):
        self.assertEqual(self._row("acme", "docker_container", "feat-x-db-1")[2], 16400)

    def test_container_of_missing_working_dir_is_orphaned(self):
        self.assertEqual(self._row("acme", "docker_container", "old-task-web-1")[4], "orphaned")
        self.assertEqual(self._row("acme", "docker_container", "old-task-db-1")[4], "orphaned")

    def test_container_of_another_project_checkout_is_not_orphaned(self):
        self.assertEqual(self._row("zeta", "docker_container", "zeta-db-1")[4], "")

    def test_unlabeled_container_is_unattributed_without_flag(self):
        row = self._row(None, "docker_container", "standalone-redis")
        self.assertEqual((row[3], row[4], row[5]), ("ok", "", ""))


class AttributeVolumeTests(unittest.TestCase):
    def setUp(self):
        self.result = _attribute(_fixture_df())

    def _row(self, project, item):
        return _rows_by_item(self.result[project])[("docker_volume", item)]

    def test_volume_of_a_known_compose_project_follows_its_owner(self):
        self.assertEqual(self._row("acme", "feat-x_postgres_data")[4:], ["", "feat-x"])

    def test_volume_of_orphaned_compose_project_is_flagged(self):
        self.assertEqual(self._row("acme", "old-task_postgres_data")[4], "orphaned")

    def test_volume_matching_an_existing_worktree_name_is_owned_without_flag(self):
        row = self._row("acme", "feat-y_postgres_data")
        self.assertEqual((row[2], row[4]), (88000000, ""))

    def test_volume_of_unknown_compose_project_is_unattributed_and_orphaned(self):
        row = self._row(None, "gone-task_postgres_data")
        self.assertEqual((row[2], row[3], row[4]), (None, "unavailable", "orphaned"))

    def test_volume_without_label_is_unattributed_and_not_flagged(self):
        self.assertEqual(self._row(None, "loose_volume")[4], "")


class AttributeImageTests(unittest.TestCase):
    def setUp(self):
        self.result = _attribute(_fixture_df())

    def _row(self, project, item):
        return _rows_by_item(self.result[project])[("docker_image", item)]

    def test_image_of_a_live_container_follows_its_owner_with_unique_size(self):
        row = self._row("acme", "feat-x-web:latest")
        self.assertEqual((row[2], row[3], row[4]), (64690000, "ok", ""))

    def test_image_is_orphaned_when_all_its_containers_are_orphaned(self):
        self.assertEqual(self._row("acme", "old-task-web:latest")[4], "orphaned")

    def test_image_shared_by_containers_of_different_owners_is_unattributed(self):
        row = self._row(None, "postgres:18")
        self.assertEqual((row[2], row[4]), (0, ""))

    def test_image_without_container_is_matched_by_compose_name_prefix(self):
        row = self._row(None, "gone-task-web:latest")
        self.assertEqual((row[2], row[4]), (900000000, "orphaned"))

    def test_dangling_image_uses_short_id_and_wins_over_unused(self):
        row = self._row(None, "5e6f7a8b9c0d")
        self.assertEqual((row[2], row[4]), (1400000000, "dangling"))

    def test_unused_image_without_other_signal(self):
        row = self._row(None, "scratch-tool:1")
        self.assertEqual((row[2], row[4]), (18490, "unused"))

    def test_image_of_an_unlabeled_container_stays_unattributed_and_unflagged(self):
        self.assertEqual(self._row(None, "redis:7")[4], "")

    def test_every_row_has_six_fields_and_items_are_unique_per_category(self):
        seen = set()
        for rows in self.result.values():
            for row in rows:
                self.assertEqual(len(row), 6)
                key = (row[0], row[1])
                self.assertNotIn(key, seen)
                seen.add(key)


class AttributeEdgeTests(unittest.TestCase):
    def test_empty_arrays_produce_no_rows(self):
        self.assertEqual(_attribute({"Images": [], "Containers": [], "Volumes": [], "BuildCache": []}), {})

    def test_missing_arrays_produce_no_rows(self):
        self.assertEqual(_attribute({}), {})

    def test_item_without_size_is_unavailable_not_a_crash(self):
        df = {"Images": [{"ID": "sha256:" + "a" * 64, "Repository": "acme-web", "Tag": "latest"}]}
        row = _attribute(df)[None][0]
        self.assertEqual(row[2:4], [None, "unavailable"])

    def test_not_available_size_is_unavailable(self):
        df = {"Volumes": [{"Name": "acme_data", "Labels": "", "Size": "N/A"}]}
        self.assertEqual(_attribute(df)[None][0][2:4], [None, "unavailable"])

    def test_container_without_names_falls_back_to_short_id(self):
        df = {"Containers": [{"ID": "abcdef0123456789", "Image": "redis:7", "Labels": "", "Size": "1kB"}]}
        self.assertEqual(_attribute(df)[None][0][1], "abcdef012345")

    def test_longest_root_wins_and_ties_go_to_the_alphabetically_first_project(self):
        roots = {"beta": ["/srv/shared"], "alpha": ["/srv/shared"], "gamma": ["/srv"]}
        df = {
            "Containers": [
                {
                    "ID": "a" * 12,
                    "Names": "x-web-1",
                    "Image": "x-web",
                    "State": "running",
                    "Size": "1kB",
                    "Labels": "com.docker.compose.project.working_dir=/srv/shared/x,com.docker.compose.project=x",
                }
            ]
        }
        result = docker.attribute(df, roots, {}, lambda path: True)
        self.assertEqual(list(result), ["alpha"])

    def test_root_match_respects_component_boundaries(self):
        roots = {"acme": ["/home/u/acme/app"]}
        df = {
            "Containers": [
                {
                    "ID": "a" * 12,
                    "Names": "x-web-1",
                    "Image": "x-web",
                    "State": "running",
                    "Size": "1kB",
                    "Labels": "com.docker.compose.project.working_dir=/home/u/acme/app-live,com.docker.compose.project=x",
                }
            ]
        }
        result = docker.attribute(df, roots, {}, lambda path: True)
        self.assertEqual(list(result), [None])

    def test_compose_name_matches_normalized_worktree_basename(self):
        checkouts = {"acme": ["/home/u/acme/app/.claude/worktrees/PTD 12_a"]}
        roots = {"acme": ["/home/u/acme/app/.claude/worktrees/PTD 12_a"]}
        df = {"Volumes": [{"Name": "ptd12_a_data", "Labels": "com.docker.compose.project=ptd12_a", "Size": "1kB"}]}
        result = docker.attribute(df, roots, checkouts, lambda path: True)
        self.assertEqual(result["acme"][0][4], "")


if __name__ == "__main__":
    unittest.main()
