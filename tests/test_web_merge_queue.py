import http.client
import json
import threading
from pathlib import Path

from guild import context, db, paths, timeutil, webserver
from guild.commands import board as board_commands
from tests.mq_fixtures import TASKS_MD, MergeQueueTestCase, diff_fixture

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_ES = "config/locales/es.yml"


class MergeQueueModelTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        for name, session in (("alpha", "sess-1"), ("beta", "sess-2"), ("gamma", "sess-3"), ("delta", "sess-4")):
            self.start_party(name, session)
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T03")
        self.add_quest("sess-2", "qb", "demo-epic", "T02")
        self.run_cli(["quest", "add", "qc", "--title", "qc", "--no-epic"], "sess-3", self.repo_dir)
        self.run_cli(["task", "add", "qc/T01", "--title", "t"], "sess-3", self.repo_dir)
        self.track("sess-1", 1, "qa/T03", "ready")
        self.track("sess-2", 2, "qb/T02", "ready")
        self.track("sess-2", 3, "qb/T02", "draft")
        self.track("sess-3", 4, "qc/T01", "ready")
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "empty", "--until-leave"], "sess-4", self.repo_dir)
        self.write_gh_fixture("view_files_acme-app_1", diff_fixture([_ES], 9, 1, "2026-09-01T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_2", diff_fixture([_ES], 1, 1, "2026-09-02T10:00:00Z"))
        self.write_gh_fixture("view_files_acme-app_3", diff_fixture([], 1, 1, "2026-09-02T10:00:00Z"))
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)

    def model(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), None,
        )
        try:
            return board_commands.board_model(ctx)
        finally:
            conn.close()

    def queues_by_scope(self):
        return {queue["scope"]: queue for queue in self.model()["merge_queues"]}


class MergeQueueModelTests(MergeQueueModelTestCase):
    def test_one_queue_per_raid_and_per_open_party_outside_raids(self):
        self.assertEqual(
            [queue["scope"] for queue in self.model()["merge_queues"]],
            ["raid:ci", "raid:empty", "party:gamma"],
        )

    def test_queue_shape(self):
        queue = self.queues_by_scope()["raid:ci"]
        self.assertEqual(set(queue), {"scope", "synced_at", "synced_label", "queue", "blocked"})
        timeutil.from_iso(queue["synced_at"])
        self.assertEqual(queue["synced_label"], "synced 0 min ago")

    def test_queue_entry_shape_and_order(self):
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        self.assertEqual([entry["ref"] for entry in queue], ["acme/app#2", "acme/app#1"])
        first = queue[0]
        self.assertEqual(
            set(first),
            {
                "position", "ref", "repo", "number", "party", "task", "lifecycle",
                "checks_failing", "checks_passing", "reason", "url",
            },
        )
        self.assertEqual([entry["position"] for entry in queue], [1, 2])
        self.assertEqual(first["url"], "https://github.com/acme/app/pull/2")
        self.assertEqual(first["party"], "beta")
        self.assertEqual(first["task"], "qb/T02")
        self.assertEqual(first["lifecycle"], "ready")
        self.assertIn("before acme/app#1 (shares config/locales/es.yml, smaller diff)", first["reason"])

    def test_blocked_entry_shape(self):
        blocked = self.queues_by_scope()["raid:ci"]["blocked"]
        self.assertEqual([entry["ref"] for entry in blocked], ["acme/app#3"])
        self.assertEqual(
            set(blocked[0]),
            {"ref", "repo", "number", "party", "task", "lifecycle", "checks_failing", "checks_passing", "reasons", "url"},
        )
        self.assertEqual(blocked[0]["reasons"], ["draft"])

    def test_raid_without_open_prs_has_an_empty_queue(self):
        queue = self.queues_by_scope()["raid:empty"]
        self.assertEqual((queue["queue"], queue["blocked"], queue["synced_at"]), ([], [], None))
        self.assertEqual(queue["synced_label"], "never synced")

    def test_party_outside_raids_gets_its_own_queue(self):
        queue = self.queues_by_scope()["party:gamma"]
        self.assertEqual([entry["ref"] for entry in queue["queue"]], ["acme/app#4"])

    def test_party_outside_raids_without_prs_has_no_queue(self):
        self.start_party("omega", "sess-9")
        self.assertNotIn("party:omega", self.queues_by_scope())

    def test_pin_changes_the_model_order(self):
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#1", "--before", "acme/app#2"], None, self.repo_dir
        )
        self.assertEqual(code, 0, err)
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        self.assertEqual([entry["ref"] for entry in queue], ["acme/app#1", "acme/app#2"])
        self.assertIn("pinned before acme/app#2 by human", queue[0]["reason"])

    def test_model_is_json_serializable(self):
        json.dumps(self.model())


class ServerMergeQueueTests(MergeQueueModelTestCase):
    def test_api_board_serves_merge_queues(self):
        server = webserver.start(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/board", headers={"Host": "127.0.0.1:{}".format(port)})
            body = json.loads(conn.getresponse().read())
            conn.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.assertEqual([queue["scope"] for queue in body["merge_queues"]], ["raid:ci", "raid:empty", "party:gamma"])


class MergeQueuePageTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.js = (_WEB_DIR / "app.js").read_text()
        self.html = (_WEB_DIR / "index.html").read_text()
        self.css = (_WEB_DIR / "app.css").read_text()

    def test_page_has_a_merge_queue_section_above_the_parties(self):
        self.assertIn('id="merge-queues"', self.html)
        self.assertLess(self.html.index('id="merge-queues"'), self.html.index('id="parties"'))

    def test_page_renders_the_queue_with_lifecycle_pills_and_links(self):
        self.assertIn("function renderMergeQueues", self.js)
        self.assertIn('"pill lifecycle-" + entry.lifecycle', self.js)
        self.assertIn("merge_queues", self.js)

    def test_page_filters_queues_by_raid_and_party(self):
        self.assertIn('"raid:" + state.raidFilter', self.js)
        self.assertIn("filterMergeQueuesByParty", self.js)

    def test_page_says_guild_never_merges(self):
        self.assertIn("guild never merges", self.js)

    def test_queue_markup_uses_only_text_content(self):
        start = self.js.index("function renderMergeQueues")
        end = self.js.index("function prMatchesStateFilter")
        section = self.js[start:end]
        for banned in ("innerHTML", "insertAdjacentHTML", "outerHTML", ".style", "setAttribute"):
            self.assertNotIn(banned, section)
        self.assertIn(".textContent", self.js)

    def test_css_styles_the_queue_list(self):
        self.assertIn("ol.queue-list", self.css)
