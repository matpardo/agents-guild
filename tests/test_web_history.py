import json
from datetime import datetime, timedelta, timezone

from guild import db, paths
from tests.test_web_server import WebServerTestCase

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(hours):
    return (_T0 + timedelta(hours=hours)).isoformat()


class HistoryRouteTests(WebServerTestCase):
    def _host(self):
        return "127.0.0.1:{}".format(self.port)

    def _seed_event(self, event_id, hours, party, project, kind, payload):
        conn = db.connect(paths.db_path())
        conn.execute(
            "INSERT INTO events (id, ts, origin, party, session_id, project, kind, visibility, payload)"
            " VALUES (?, ?, 'test@host', ?, NULL, ?, ?, 'local', ?)",
            (event_id, _at(hours), party, project, kind, json.dumps(payload)),
        )
        conn.commit()
        conn.close()

    def _seed_done_quest(self, slug, party, project):
        self._seed_event("added-" + slug, 0, party, project, "quest.added", {
            "slug": slug, "project": project, "party": party, "epic": None, "title": "Quest " + slug,
            "tasks": [],
        })
        self._seed_event("done-" + slug, 5, party, project, "quest.done", {"slug": slug})

    def _get_history(self, query):
        response, body = self._get("/api/history" + query, self._host())
        return response, json.loads(body)

    def test_history_page_is_served_as_html(self):
        response, body = self._get("/history", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertIn(b"<!DOCTYPE html>", body)
        self.assertIn(b'src="/history.js"', body)

    def test_history_js_is_served_as_javascript(self):
        response, body = self._get("/history.js", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/javascript; charset=utf-8")
        self.assertTrue(body)

    def test_board_page_links_to_history(self):
        response, body = self._get("/", self._host())
        self.assertIn(b'href="/history"', body)

    def test_history_page_links_back_to_board(self):
        response, body = self._get("/history", self._host())
        self.assertIn(b'href="/"', body)

    def test_api_history_returns_model_shape_when_empty(self):
        response, model = self._get_history("")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(model["quests"], [])
        self.assertEqual(model["raids"], [])
        self.assertEqual(model["totals"]["quests_done"], 0)

    def test_api_history_lists_completed_quests(self):
        self._seed_done_quest("q1", "alpha", "acme")
        response, model = self._get_history("")
        self.assertEqual([quest["slug"] for quest in model["quests"]], ["q1"])
        self.assertFalse(model["quests"][0]["snapshot"])
        self.assertEqual(model["totals"]["quests_done"], 1)

    def test_api_history_filters_by_party(self):
        self._seed_done_quest("q1", "alpha", "acme")
        self._seed_done_quest("q2", "beta", "acme")
        response, model = self._get_history("?party=beta")
        self.assertEqual([quest["slug"] for quest in model["quests"]], ["q2"])

    def test_api_history_filters_by_project(self):
        self._seed_done_quest("q1", "alpha", "acme")
        self._seed_done_quest("q2", "beta", "other")
        response, model = self._get_history("?project=other")
        self.assertEqual([quest["slug"] for quest in model["quests"]], ["q2"])

    def test_api_history_ignores_unknown_query_params(self):
        self._seed_done_quest("q1", "alpha", "acme")
        response, model = self._get_history("?bogus=1")
        self.assertEqual(len(model["quests"]), 1)

    def test_page_has_in_progress_and_incomplete_sections(self):
        response, body = self._get("/history", self._host())
        self.assertIn(b'id="active-quests"', body)
        self.assertIn(b'id="incomplete-quests"', body)
        self.assertLess(body.index(b'id="active-quests"'), body.index(b'id="quests"'))
        self.assertLess(body.index(b'id="quests"'), body.index(b'id="incomplete-quests"'))

    def test_js_renders_new_sections(self):
        response, body = self._get("/history.js", self._host())
        self.assertIn(b"nothing in progress", body)
        self.assertIn(b"Closed without completing", body)

    def test_api_exposes_new_lists_when_empty(self):
        response, model = self._get_history("")
        self.assertEqual(model["active_quests"], [])
        self.assertEqual(model["incomplete_quests"], [])

    def test_api_lists_incomplete_quest(self):
        self._seed_done_quest("q1", "alpha", "acme")
        self._seed_event("mark-q1", 6, "alpha", "acme", "quest.marked_incomplete", {"slug": "q1", "reason": "r"})
        response, model = self._get_history("")
        self.assertEqual(model["quests"], [])
        self.assertEqual([quest["slug"] for quest in model["incomplete_quests"]], ["q1"])
