import json

from tests.test_web_write import WebWriteTestCase


class WebIdeaTests(WebWriteTestCase):
    def _ideas(self):
        response, body = self._get("/api/board", self._host())
        return json.loads(body)["ideas"]

    def _create(self, **overrides):
        data = {"title": "Dark mode", "description": "night owls"}
        data.update(overrides)
        return self._post_json("/api/ideas/create", self._good_headers(), data)

    def test_board_lists_every_registered_project_name(self):
        response, body = self._get("/api/board", self._host())
        self.assertEqual(json.loads(body)["project_names"], ["acme"])

    def test_create_edit_delete(self):
        response, payload = self._create(deadline="2000-01-01", project="acme")
        self.assertEqual(response.status, 200, payload)
        idea = self._ideas()[0]
        self.assertEqual((idea["title"], idea["project"], idea["overdue"]), ("Dark mode", "acme", True))
        response, payload = self._post_json(
            "/api/ideas/1/edit", self._good_headers(), {"title": "Light mode", "deadline": None}
        )
        self.assertEqual(response.status, 200, payload)
        idea = self._ideas()[0]
        self.assertEqual((idea["title"], idea["deadline"], idea["overdue"]), ("Light mode", None, False))
        response, payload = self._post_json("/api/ideas/1/delete", self._good_headers(), {})
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._ideas(), [])

    def test_invalid_input_is_422(self):
        for overrides in ({"deadline": "soon"}, {"project": "ghost"}, {"title": " "}):
            response, payload = self._create(**overrides)
            self.assertEqual(response.status, 422, overrides)
        response, payload = self._post_json("/api/ideas/9/delete", self._good_headers(), {})
        self.assertEqual(response.status, 422)
        response, payload = self._post_json("/api/ideas/9/edit", self._good_headers(), {})
        self.assertEqual(response.status, 422)

    def test_wrong_types_are_400(self):
        response, payload = self._create(title=3)
        self.assertEqual(response.status, 400)
        response, payload = self._create(deadline=5)
        self.assertEqual(response.status, 400)
        response, payload = self._post_json("/api/ideas/1/edit", self._good_headers(), {"title": 3})
        self.assertEqual(response.status, 400)

    def test_bad_id_is_404(self):
        response, payload = self._post_json("/api/ideas/abc/delete", self._good_headers(), {})
        self.assertEqual(response.status, 404)

    def test_missing_token_and_wrong_origin_are_403(self):
        body = {"title": "x", "description": "y"}
        headers = self._good_headers()
        del headers["X-Guild-Token"]
        self.assertEqual(self._post_json("/api/ideas/create", headers, body)[0].status, 403)
        headers = self._good_headers()
        headers["Origin"] = "http://evil.example"
        self.assertEqual(self._post_json("/api/ideas/create", headers, body)[0].status, 403)
        self.assertEqual(self._ideas(), [])


class WebIdeaLinkTests(WebWriteTestCase):
    def setUp(self):
        super().setUp()
        self._post_json("/api/ideas/create", self._good_headers(), {"title": "Dark mode", "description": "d"})

    def _link(self, action, **data):
        return self._post_json("/api/ideas/1/" + action, self._good_headers(), data)

    def _board(self):
        return json.loads(self._get("/api/board", self._host())[1])

    def test_link_and_unlink(self):
        response, payload = self._link("link", party="alpha")
        self.assertEqual(response.status, 200, payload)
        board = self._board()
        self.assertEqual(board["ideas"][0]["parties"], [{"name": "alpha", "state": "active", "has_prs": False}])
        self.assertEqual(board["parties"][0]["ideas"], [{"id": 1, "title": "Dark mode"}])
        response, payload = self._link("unlink", party="alpha")
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._board()["ideas"][0]["parties"], [])

    def _start_adventurer(self):
        self.run_cli(
            ["quest", "add", "chore", "--open", "--no-epic", "--title", "chore", "--tasks", "T01", "--titles", "one"],
            None,
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["adventurer", "start", "fix typo", "--task", "chore/T01", "--reason", "test reason"],
            "adv-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def test_adventurer_link_and_unlink(self):
        self._start_adventurer()
        response, payload = self._link("link", adventurer=1)
        self.assertEqual(response.status, 200, payload)
        board = self._board()
        self.assertEqual(board["ideas"][0]["adventurers"], [{"id": 1, "state": "active", "has_prs": False}])
        self.assertEqual(board["adventurers"][0]["ideas"], [{"id": 1, "title": "Dark mode"}])
        response, payload = self._link("unlink", adventurer=1)
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(self._board()["ideas"][0]["adventurers"], [])

    def test_adventurer_refusals_are_422_and_bad_payloads_400(self):
        self.assertEqual(self._link("link", adventurer=9)[0].status, 422)
        self.assertEqual(self._link("link", adventurer="1")[0].status, 400)
        self.assertEqual(self._link("link", adventurer=True)[0].status, 400)
        self.assertEqual(self._link("link", adventurer=1, party="alpha")[0].status, 400)
        self.assertEqual(self._link("unlink", adventurer=None)[0].status, 400)

    def test_unlink_is_422_once_the_party_tracks_a_pr(self):
        self._link("link", party="alpha")
        self.write_gh_fixture(
            "view_acme-app_7",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/7", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#7", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        response, payload = self._link("unlink", party="alpha")
        self.assertEqual(response.status, 422, payload)
        self.assertIn(b"the party already tracks a PR", payload)
        self.assertEqual(self._board()["ideas"][0]["parties"][0]["has_prs"], True)

    def test_refusals_are_422_and_bad_types_400(self):
        self.assertEqual(self._link("link", party="ghost")[0].status, 422)
        self._link("link", party="alpha")
        self.assertEqual(self._link("link", party="alpha")[0].status, 422)
        self.assertEqual(self._link("unlink", party="zeta")[0].status, 422)
        self.assertEqual(self._link("link", party=3)[0].status, 400)
        self.assertEqual(self._link("link")[0].status, 400)
