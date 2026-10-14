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
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
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
        self.assertEqual(set(queue), {"scope", "head", "synced_at", "synced_label", "main", "queue"})
        timeutil.from_iso(queue["synced_at"])
        self.assertEqual(queue["synced_label"], "synced 0 min ago")

    def test_head_names_the_first_ready_pr_and_its_party(self):
        queues = self.queues_by_scope()
        head = queues["raid:ci"]["head"]
        self.assertEqual((head["ref"], head["party"]), ("acme/app#1", "alpha"))
        self.assertEqual(head["url"], "https://github.com/acme/app/pull/1")
        self.assertIsNone(queues["raid:empty"]["head"])

    def test_draft_entry_carries_its_gate(self):
        entries = {entry["ref"]: entry for entry in self.queues_by_scope()["raid:ci"]["queue"]}
        self.assertEqual(entries["acme/app#3"]["gates"], ["draft (gh pr ready 3)"])
        self.assertEqual(entries["acme/app#1"]["gates"], [])

    def test_queue_entry_shape_and_order(self):
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        self.assertEqual([entry["ref"] for entry in queue], ["acme/app#1", "acme/app#2", "acme/app#3"])
        first = queue[0]
        self.assertEqual(
            set(first),
            {
                "position", "ref", "repo", "number", "party", "task", "lifecycle", "branch",
                "checks_failing", "checks_passing", "checks_pending", "labels", "blocked_external", "unblocks", "state", "next_action",
                "action", "why", "reasons", "blockers", "waits", "gates", "url", "fix_reasons", "fix_request",
            },
        )
        self.assertEqual([entry["position"] for entry in queue], [1, 2, 3])
        self.assertEqual(first["url"], "https://github.com/acme/app/pull/1")
        self.assertEqual(first["party"], "alpha")
        self.assertEqual(first["task"], "qa/T03")
        self.assertEqual(first["lifecycle"], "ready")
        self.assertEqual(first["branch"], "feature/x")
        self.assertEqual((first["state"], first["action"], first["reasons"]), ("ready", "merge", []))
        self.assertEqual(first["unblocks"], 1)

    def test_draft_entry_is_ready_with_a_label_and_a_promote_action(self):
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        draft = [entry for entry in queue if entry["ref"] == "acme/app#3"][0]
        self.assertEqual(
            (draft["state"], draft["labels"], draft["reasons"], draft["checks_pending"]),
            ("ready", ["draft"], [], 0),
        )
        self.assertEqual(draft["action"], "promote: gh pr ready \u2192 beta")

    def test_blocked_entry_stays_in_the_queue_with_its_action(self):
        self.run_cli(["pr", "set", "acme/app#3", "--needs-ask-answer"], "sess-2", self.repo_dir)
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        blocked = [entry for entry in queue if entry["state"] == "blocked"]
        self.assertEqual([entry["ref"] for entry in blocked], ["acme/app#3"])
        self.assertEqual(blocked[0]["reasons"], ["needs ask answer"])
        self.assertEqual(blocked[0]["labels"], ["draft", "needs-ask-answer"])
        self.assertEqual(blocked[0]["action"], "fix: needs ask answer \u2192 beta")
        self.assertFalse(blocked[0]["next_action"])

    def test_blocked_externally_entry_carries_its_own_reason(self):
        self.run_cli(["pr", "set", "acme/app#3", "--blocked-external", "waiting on legal"], "sess-2", self.repo_dir)
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        reasons = {entry["ref"]: entry["blocked_external"] for entry in queue}
        self.assertEqual(reasons["acme/app#3"], "waiting on legal")
        self.assertEqual(reasons["acme/app#1"], None)

    def test_raid_without_open_prs_has_an_empty_queue(self):
        queue = self.queues_by_scope()["raid:empty"]
        self.assertEqual((queue["queue"], queue["main"], queue["synced_at"]), ([], [], None))
        self.assertEqual(queue["synced_label"], "never synced")

    def test_red_main_is_listed_for_scopes_with_prs_in_that_repo(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        queues = self.queues_by_scope()
        self.assertEqual(
            queues["raid:ci"]["main"], [{"repo": "acme/app", "source": "manual", "reason": "ci down", "external": None}]
        )
        self.assertEqual(queues["raid:empty"]["main"], [])

    def test_billing_blocked_main_carries_its_external_cause(self):
        self.mark_billing_blocked()
        self.assertEqual(
            self.queues_by_scope()["raid:ci"]["main"],
            [{"repo": "acme/app", "source": "gh", "reason": "checks failing: lint", "external": "billing"}],
        )

    def test_party_outside_raids_gets_its_own_queue(self):
        queue = self.queues_by_scope()["party:gamma"]
        self.assertEqual([entry["ref"] for entry in queue["queue"]], ["acme/app#4"])

    def test_party_outside_raids_without_prs_has_no_queue(self):
        self.start_party("omega", "sess-9")
        self.assertNotIn("party:omega", self.queues_by_scope())

    def test_pin_changes_the_model_order(self):
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#2", "--before", "acme/app#1"], None, self.repo_dir
        )
        self.assertEqual(code, 0, err)
        queue = self.queues_by_scope()["raid:ci"]["queue"]
        self.assertEqual([entry["ref"] for entry in queue], ["acme/app#2", "acme/app#1", "acme/app#3"])
        self.assertIn("pinned before acme/app#1 by human", queue[0]["why"])

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
        self.assertIn('"pill lifecycle-" + label', self.js)
        self.assertIn("entry.labels.forEach", self.js)
        self.assertIn("merge_queues", self.js)

    def test_page_renders_reason_pills_ready_check_detail_and_next_to_merge(self):
        for token in ("renderReasonPills(entry.reasons)", "entry.gates", "entry.blockers", "entry.waits",
                      "next to merge: ", "no PR ready to merge", "queue.head", "state.queueDetailOpen"):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_page_filters_queues_by_raid_and_party(self):
        self.assertIn('"raid:" + state.raidFilter', self.js)
        self.assertIn("filterMergeQueuesByParty", self.js)

    def test_page_renders_one_list_with_state_unblocks_action_and_main_row(self):
        self.assertIn("entry.unblocks", self.js)
        self.assertIn("entry.action", self.js)
        self.assertIn("next action", self.js)
        self.assertIn("queue.main.map(renderMainRow)", self.js)
        self.assertNotIn("queue.blocked", self.js)

    def test_page_styles_waiting_entries_and_pending_checks(self):
        self.assertIn("checks-pending", self.js)
        self.assertRegex(self.css, r"(?m)^li\.queue-waiting > \.queue-reason\s*\{")
        self.assertRegex(self.css, r"(?m)^\.checks-pending\s*\{")

    def test_page_tags_ready_entries_with_a_green_ready_pill(self):
        self.assertIn('entry.state === "ready"', self.js)
        self.assertIn('entry.labels.indexOf("draft") === -1', self.js)
        self.assertIn("renderReadyPill()", self.js)
        self.assertRegex(self.css, r"(?m)^\.lifecycle-ready\s*\{")

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
