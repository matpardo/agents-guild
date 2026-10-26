import json
import unittest

from guild import db, events, reducers
from guild.cli import _build_context
from tests.testutil import GuildTestCase

_DOCKER = {
    "images": 100,
    "images_reclaimable": 40,
    "containers": 10,
    "volumes": 20,
    "build_cache": 5,
}


def machine_payload(docker):
    return {
        "disk_total": 500,
        "disk_used": 400,
        "mem_total": 32,
        "mem_available": 16,
        "load1": 2.5,
        "load5": 2.0,
        "load15": 1.5,
        "cpu_count": 4,
        "guild_db_bytes": 7,
        "docker": docker,
    }


def sampled_payload(items, docker):
    return {"items": items, "machine": machine_payload(docker)}


class ResourcesProjectionTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = _build_context("sess-1", self.root)

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def _record(self, project, payload):
        with db.writing(self.ctx.conn):
            return events.record(
                self.ctx.conn, self.ctx.now, self.ctx.origin, None, None, project, "resources.sampled", "local", payload
            )

    def _samples(self):
        return self.ctx.conn.execute("SELECT * FROM resource_samples ORDER BY project, ts, category, item").fetchall()

    def _machine(self):
        return self.ctx.conn.execute("SELECT * FROM resource_machine ORDER BY ts").fetchall()

    def test_event_inserts_one_row_per_item(self):
        event = self._record(
            "acme",
            sampled_payload(
                [
                    ["worktree", "/home/u/acme/app", 4096, "ok", "", "main"],
                    ["docker_image", "acme-web:latest", 900, "ok", "orphaned", ""],
                ],
                _DOCKER,
            ),
        )
        rows = self._samples()
        self.assertEqual(len(rows), 2)
        by_category = {row["category"]: row for row in rows}
        worktree = by_category["worktree"]
        self.assertEqual(
            (worktree["project"], worktree["ts"], worktree["item"], worktree["bytes"]),
            ("acme", event["ts"], "/home/u/acme/app", 4096),
        )
        self.assertEqual((worktree["state"], worktree["flag"], worktree["detail"]), ("ok", "", "main"))
        self.assertEqual(by_category["docker_image"]["flag"], "orphaned")

    def test_null_project_is_stored_as_empty_string(self):
        self._record(None, sampled_payload([["docker_volume", "acme_db", 5, "ok", "orphaned", ""]], None))
        self.assertEqual(self._samples()[0]["project"], "")

    def test_null_bytes_stay_null(self):
        self._record("acme", sampled_payload([["worktree", "/home/u/acme/app", None, "skipped", "", "main"]], None))
        row = self._samples()[0]
        self.assertIsNone(row["bytes"])
        self.assertEqual(row["state"], "skipped")

    def test_machine_row_is_written_with_docker_totals(self):
        event = self._record("acme", sampled_payload([], _DOCKER))
        row = self._machine()[0]
        self.assertEqual(row["ts"], event["ts"])
        self.assertEqual((row["disk_total"], row["disk_used"]), (500, 400))
        self.assertEqual((row["mem_total"], row["mem_available"], row["guild_db_bytes"]), (32, 16, 7))
        self.assertEqual(
            (
                row["docker_images"],
                row["docker_images_reclaimable"],
                row["docker_containers"],
                row["docker_volumes"],
                row["docker_build_cache"],
            ),
            (100, 40, 10, 20, 5),
        )

    def test_machine_load_columns_are_stored(self):
        self._record("acme", sampled_payload([], None))
        row = self._machine()[0]
        self.assertEqual((row["load1"], row["load5"], row["load15"], row["cpu_count"]), (2.5, 2.0, 1.5, 4))

    def test_old_payload_without_load_keys_replays_as_null(self):
        payload = sampled_payload([], None)
        for key in ("load1", "load5", "load15", "cpu_count"):
            del payload["machine"][key]
        self._record("acme", payload)
        row = self._machine()[0]
        self.assertEqual((row["load1"], row["load5"], row["load15"], row["cpu_count"]), (None, None, None, None))

    def test_machine_docker_null_leaves_docker_columns_null(self):
        self._record("acme", sampled_payload([], None))
        row = self._machine()[0]
        self.assertIsNone(row["docker_images"])
        self.assertIsNone(row["docker_build_cache"])

    def test_machine_upserts_by_timestamp_across_projects(self):
        self._record("acme", sampled_payload([], _DOCKER))
        self._record(None, sampled_payload([], _DOCKER))
        self.assertEqual(len(self._machine()), 1)

    def test_replaying_the_same_event_twice_is_idempotent(self):
        event = self._record(
            "acme", sampled_payload([["worktree", "/home/u/acme/app", 4096, "ok", "", "main"]], _DOCKER)
        )
        before = ([dict(row) for row in self._samples()], [dict(row) for row in self._machine()])
        with db.writing(self.ctx.conn):
            reducers.apply(self.ctx.conn, event)
        after = ([dict(row) for row in self._samples()], [dict(row) for row in self._machine()])
        self.assertEqual(before, after)

    def test_rebuild_reproduces_projections(self):
        self._record(
            "acme", sampled_payload([["worktree", "/home/u/acme/app", 4096, "ok", "merged", "feat-x"]], _DOCKER)
        )
        self._record(
            None, sampled_payload([["docker_image", "<none> 5e6f7a8b9c0d", None, "unavailable", "dangling", ""]], None)
        )
        before = ([dict(row) for row in self._samples()], [dict(row) for row in self._machine()])
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        after = ([dict(row) for row in self._samples()], [dict(row) for row in self._machine()])
        self.assertEqual(before, after)
        self.assertTrue(after[0])

    def test_export_excludes_local_samples(self):
        self._record("acme", sampled_payload([["worktree", "/home/u/acme/app", 1, "ok", "", "main"]], None))
        code, out, err = self.run_cli(["export", "--visibility", "guild"], None, None)
        self.assertEqual(code, 0, err)
        kinds = [json.loads(line)["kind"] for line in out.splitlines() if line]
        self.assertNotIn("resources.sampled", kinds)


if __name__ == "__main__":
    unittest.main()
