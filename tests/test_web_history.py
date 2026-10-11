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

    def _assert_nav(self, path):
        response, body = self._get(path, self._host())
        self.assertEqual(response.status, 200)
        for href in (b'href="/"', b'href="/progress"', b'href="/history"'):
            with self.subTest(path=path, href=href):
                self.assertIn(href, body)
        self.assertLess(body.index(b'href="/"'), body.index(b'href="/progress"'))
        self.assertLess(body.index(b'href="/progress"'), body.index(b'href="/history"'))

    def test_every_page_has_the_three_way_navigation(self):
        for path in ("/", "/progress", "/history"):
            self._assert_nav(path)

    def test_progress_page_is_served_as_html(self):
        response, body = self._get("/progress", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertIn(b'src="/progress.js"', body)
        self.assertIn(b'id="progress-table"', body)

    def test_progress_js_is_served_as_javascript(self):
        response, body = self._get("/progress.js", self._host())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/javascript; charset=utf-8")
        self.assertIn(b"/api/history", body)

    def test_progress_js_marks_stale_only_when_stale_hours_is_set(self):
        response, body = self._get("/progress.js", self._host())
        self.assertIn(b"quest.stale_hours !== null &&", body)

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

    def test_history_page_has_achievement_sections_and_no_active_quests(self):
        response, body = self._get("/history", self._host())
        self.assertNotIn(b'id="active-quests"', body)
        for section in (b'id="totals"', b'id="quests"', b'id="raids"', b'id="incomplete-quests"'):
            with self.subTest(section=section):
                self.assertIn(section, body)
        self.assertLess(body.index(b'id="quests"'), body.index(b'id="raids"'))
        self.assertLess(body.index(b'id="raids"'), body.index(b'id="incomplete-quests"'))

    def test_history_js_renders_achievement_views(self):
        response, body = self._get("/history.js", self._host())
        self.assertIn(b"Closed without completing", body)
        self.assertIn(b"partial data", body)
        self.assertNotIn(b"nothing in progress", body)

    def test_history_js_labels_the_epic_bar_with_done_over_total(self):
        response, body = self._get("/history.js", self._host())
        self.assertIn(b'progress.done + "/" + progress.total', body)

    def test_api_active_quest_exposes_activity_and_stale_hours(self):
        self._seed_event("added-wip", 0, "alpha", "acme", "quest.added", {
            "slug": "wip", "project": "acme", "party": "alpha", "epic": None, "title": "Quest wip",
            "tasks": [{"tid": "T01", "title": "T01"}],
        })
        conn = db.connect(paths.db_path())
        conn.execute(
            "INSERT INTO quests (slug, party, project, epic, title, state) VALUES ('wip', 'alpha', 'acme', NULL, 'Quest wip', 'active')"
        )
        conn.commit()
        conn.close()
        response, model = self._get_history("")
        quest = model["active_quests"][0]
        self.assertIsNone(quest["stale_hours"])
        self.assertEqual(quest["last_activity_at"], _at(0))
        self.assertIn("week_totals", model)
        self.assertIn("since", model)

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
