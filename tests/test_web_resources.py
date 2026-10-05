import json
import unittest
from datetime import timedelta

from guild import db, events, paths, timeutil
from tests.test_web_server import WebServerTestCase

_GB = 1000000000
_MACHINE = {
    "disk_total": 500 * _GB,
    "disk_used": 400 * _GB,
    "mem_total": 31 * _GB,
    "mem_available": 9 * _GB,
    "guild_db_bytes": 1000,
    "docker": None,
}


class ResourcesRouteTests(WebServerTestCase):
    def setUp(self):
        super().setUp()
        self.register_project("acme", ["acme/app"])

    def _host(self):
        return "127.0.0.1:{}".format(self.port)

    def _seed(self, project, minutes_ago, size):
        conn = db.connect(paths.db_path())
        with db.writing(conn):
            events.record(
                conn,
                timeutil.utcnow() - timedelta(minutes=minutes_ago),
                "tester@host",
                None,
                None,
                project,
                "resources.sampled",
                "local",
                {
                    "items": [["worktree", "/home/u/acme/app", size, "ok", "merged", "feat-x"]],
                    "machine": _MACHINE,
                },
            )
        conn.close()

    def _get_resources(self, query):
        response, body = self._get("/api/resources" + query, self._host())
        return response, json.loads(body)

    def test_shape_matches_the_report_model(self):
        self._seed("acme", 3000, 3 * _GB)
        self._seed("acme", 5, 5 * _GB)
        self._seed(None, 5, 1 * _GB)
        response, model = self._get_resources("")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(set(model), {"generated_at", "since", "machine", "projects", "unattributed"})
        self.assertEqual(model["since"], "1d")
        self.assertEqual(
            set(model["machine"]),
            {
                "sampled_at",
                "disk_total",
                "disk_used",
                "disk_percent",
                "disk_delta",
                "mem_total",
                "mem_available",
                "guild_db_bytes",
                "docker",
                "untracked_growth",
            },
        )
        project = model["projects"][0]
        self.assertEqual(
            set(project),
            {
                "name",
                "sampled_at",
                "baseline_at",
                "baseline_oldest",
                "total_bytes",
                "delta_bytes",
                "categories",
                "items",
                "growers",
            },
        )
        self.assertEqual(project["name"], "acme")
        self.assertEqual(project["total_bytes"], 5 * _GB)
        self.assertEqual(project["delta_bytes"], 2 * _GB)
        self.assertEqual(
            set(project["categories"][0]), {"category", "bytes", "delta_bytes", "state", "detail"}
        )
        self.assertEqual(
            set(project["items"][0]),
            {"category", "item", "bytes", "delta_bytes", "new", "state", "flag", "detail"},
        )
        self.assertEqual(project["items"][0]["flag"], "merged")
        self.assertEqual(set(project["growers"][0]), {"category", "item", "delta_bytes"})
        self.assertNotIn("name", model["unattributed"])

    def test_since_and_project_are_read_from_the_query(self):
        self._seed("acme", 5, 5 * _GB)
        response, model = self._get_resources("?project=acme&since=3d")
        self.assertEqual(response.status, 200)
        self.assertEqual(model["since"], "3d")
        self.assertEqual([entry["name"] for entry in model["projects"]], ["acme"])
        self.assertIsNone(model["unattributed"])

    def test_unknown_project_is_a_client_error(self):
        response, body = self._get_resources("?project=nope")
        self.assertEqual(response.status, 422)
        self.assertIn("unknown project 'nope'", body["error"])

    def test_invalid_since_is_a_client_error(self):
        response, body = self._get_resources("?since=soon")
        self.assertEqual(response.status, 422)
        self.assertIn("invalid duration", body["error"])

    def test_no_samples_gives_an_empty_model(self):
        response, model = self._get_resources("")
        self.assertEqual(response.status, 200)
        self.assertEqual((model["projects"], model["unattributed"], model["machine"]), ([], None, None))

    def test_wrong_host_is_rejected(self):
        response, body = self._get("/api/resources", "evil.example")
        self.assertIn(response.status, (421, 403))

    def test_board_model_does_not_carry_resources(self):
        self._seed("acme", 5, 5 * _GB)
        response, body = self._get("/api/board", self._host())
        self.assertNotIn("resources", json.loads(body))

    def test_page_has_a_resources_section_and_script_fetches_the_endpoint(self):
        response, body = self._get("/", self._host())
        self.assertIn(b'id="resources"', body)
        response, script = self._get("/app.js", self._host())
        self.assertIn(b'"/api/resources"', script)

    def test_machine_lines_stay_visible_and_only_projects_collapse(self):
        response, body = self._get("/app.js", self._host())
        script = body.decode()
        render = script[script.index("function renderResources(model)"):script.index("function fetchResources()")]
        self.assertNotIn('el("details")', render)
        self.assertIn("renderResourceProjects(model)", render)
        self.assertIn('textEl("summary", "projects")', script)


if __name__ == "__main__":
    unittest.main()
