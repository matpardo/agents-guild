import json

from tests.mq_fixtures import TASKS_MD
from tests.test_web_write import WebWriteTestCase


class WebQuestBoardTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)

    def _board(self):
        return json.loads(self._get("/api/board", self._host())[1])

    def _quest_board(self):
        return self._board()["quest_boards"][0]

    def _create(self, **overrides):
        data = {"project": "acme", "slug": "pre", "title": "Pre", "epic": "demo-epic", "tasks": ["T02", "T03"]}
        data.update(overrides)
        return self._post_json("/api/quests/create-open", self._good_headers(), data)

    def test_model_lists_free_tasks_and_active_parties(self):
        quest_board = self._quest_board()
        self.assertEqual(quest_board["open_quests"], [])
        self.assertEqual(quest_board["parties"], ["alpha"])
        self.assertIn("T02", [task["tid"] for task in quest_board["free_tasks"][0]["tasks"]])

    def test_create_open_quest_then_take_then_release(self):
        response, payload = self._create()
        self.assertEqual(response.status, 200, payload)
        quest_board = self._quest_board()
        self.assertEqual([quest["slug"] for quest in quest_board["open_quests"]], ["pre"])
        self.assertEqual([task["tid"] for task in quest_board["open_quests"][0]["tasks"]], ["T02", "T03"])
        free = [task["tid"] for entry in quest_board["free_tasks"] for task in entry["tasks"]]
        self.assertNotIn("T02", free)
        response, payload = self._post_json("/api/quests/pre/take", self._good_headers(), {"party": "alpha"})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._quest_board()["open_quests"], [])
        party = self._board()["parties"][0]
        quest = [quest for quest in party["quests"] if quest["slug"] == "pre"][0]
        self.assertTrue(quest["releasable"])
        response, payload = self._post_json("/api/quests/pre/release", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual([quest["slug"] for quest in self._quest_board()["open_quests"]], ["pre"])

    def test_refusals_are_422(self):
        self.assertEqual(self._create(tasks=[])[0].status, 422)
        self.assertEqual(self._create(tasks=["T99"])[0].status, 422)
        self.assertEqual(self._create(project="ghost")[0].status, 422)
        self._create()
        self.assertEqual(self._create()[0].status, 422)
        self.assertEqual(self._create(slug="other", tasks=["T02"])[0].status, 422)
        response, payload = self._post_json("/api/quests/pre/take", self._good_headers(), {"party": "ghost"})
        self.assertEqual(response.status, 422)
        response, payload = self._post_json("/api/quests/pre/release", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_bad_payloads_are_400(self):
        self.assertEqual(self._create(tasks="T02")[0].status, 400)
        self.assertEqual(self._create(tasks=[2])[0].status, 400)
        self.assertEqual(self._create(slug=3)[0].status, 400)
        response, payload = self._post_json("/api/quests/pre/take", self._good_headers(), {})
        self.assertEqual(response.status, 400)

    def test_missing_token_is_403(self):
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        body = {"project": "acme", "slug": "pre", "title": "Pre", "epic": "demo-epic", "tasks": ["T02"]}
        self.assertEqual(self._post_json("/api/quests/create-open", headers, body)[0].status, 403)
        self.assertEqual(self._quest_board()["open_quests"], [])

    def test_cli_board_shows_quest_board_block(self):
        self._create()
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("QUEST BOARD", out)
        self.assertIn("open quest pre (2 tasks", out)
        self.assertIn("free tasks demo-epic:", out)


class WebQuestBoardNoPartyTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["party", "close", "--force", "--pending", "none"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_project_without_active_party_still_has_a_board(self):
        board = json.loads(self._get("/api/board", self._host())[1])
        self.assertEqual(board["parties"], [])
        self.assertEqual(board["quest_boards"][0]["name"], "acme")
        self.assertEqual(board["quest_boards"][0]["parties"], [])
        data = {"project": "acme", "slug": "pre", "title": "Pre", "epic": "demo-epic", "tasks": ["T02"]}
        self.assertEqual(self._post_json("/api/quests/create-open", self._good_headers(), data)[0].status, 200)

    def test_cli_board_shows_the_block_without_parties(self):
        code, out, err = self.run_cli(["board"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("acme QUEST BOARD", out)
        self.assertIn("free tasks demo-epic:", out)
