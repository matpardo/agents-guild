import json
import unittest
from datetime import timedelta
from pathlib import Path

from guild import db, events, paths, timeutil
from tests.test_web_server import WebServerTestCase

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"
_NOW = timeutil.utcnow()


class AnsweredAsksEndpointTests(WebServerTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.conn = db.connect(paths.db_path())
        self.host = "127.0.0.1:{}".format(self.port)

    def _answered_ask(self, ask_id, answered_at):
        with db.writing(self.conn):
            events.record(
                self.conn,
                _NOW - timedelta(days=30),
                "test@host",
                "alpha",
                None,
                "acme",
                "ask.created",
                "local",
                {
                    "id": ask_id,
                    "party": "alpha",
                    "question": "q{}?".format(ask_id),
                    "context": "x",
                    "refs": ["task:demo/T01"],
                    "options": [],
                },
            )
            events.record(
                self.conn,
                answered_at,
                "test@host",
                None,
                None,
                "acme",
                "ask.answered",
                "local",
                {"id": ask_id, "answer": "a{}".format(ask_id)},
            )

    def _seed(self, count):
        for ask_id in range(1, count + 1):
            self._answered_ask(ask_id, _NOW - timedelta(hours=count - ask_id))

    def test_returns_first_page_newest_first_with_party_and_date(self):
        self._seed(12)
        response, body = self._get("/api/asks/answered", self.host)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        model = json.loads(body)
        self.assertEqual((model["page"], model["page_count"], model["total"]), (1, 2, 12))
        self.assertEqual([ask["id"] for ask in model["asks"]], list(range(12, 2, -1)))
        first = model["asks"][0]
        self.assertEqual(set(first), {"id", "party", "question", "answer", "answered_at", "dates"})
        self.assertEqual((first["party"], first["answer"]), ("alpha", "a12"))
        self.assertTrue(first["dates"].startswith("created "))
        self.assertIn(" · updated ", first["dates"])

    def test_second_page_has_the_oldest(self):
        self._seed(12)
        response, body = self._get("/api/asks/answered?page=2", self.host)
        model = json.loads(body)
        self.assertEqual([ask["id"] for ask in model["asks"]], [2, 1])

    def test_nothing_answered_is_an_empty_model(self):
        response, body = self._get("/api/asks/answered", self.host)
        self.assertEqual(json.loads(body), {"page": 1, "page_count": 0, "total": 0, "asks": []})

    def test_open_asks_are_not_listed(self):
        self.run_cli(["ask", "Which?", "--context", "ctx", "--ref", "task:demo/T01"], "sess-1", self.repo_dir)
        response, body = self._get("/api/asks/answered", self.host)
        self.assertEqual(json.loads(body)["total"], 0)

    def test_page_out_of_range_is_422(self):
        self._seed(3)
        response, body = self._get("/api/asks/answered?page=2", self.host)
        self.assertEqual(response.status, 422)
        self.assertEqual(json.loads(body), {"error": "page 2 out of range, 1-1"})

    def test_non_numeric_page_is_422(self):
        response, body = self._get("/api/asks/answered?page=abc", self.host)
        self.assertEqual(response.status, 422)
        self.assertEqual(json.loads(body), {"error": "page must be a positive integer"})

    def test_wrong_host_is_rejected(self):
        response, body = self._get("/api/asks/answered", "evil.example")
        self.assertEqual(response.status, 421)


class AnsweredAsksSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()
        start = self.source.index("function renderAnsweredAsk(ask) {")
        end = self.source.index("function renderStatusBadge(status) {")
        self.block = self.source[start:end]

    def test_block_never_uses_inner_html(self):
        self.assertNotIn("innerHTML", self.block)

    def test_pages_are_fetched_from_the_answered_endpoint(self):
        self.assertIn('var ANSWERED_ASKS_URL = "/api/asks/answered";', self.source)
        self.assertIn('ANSWERED_ASKS_URL + "?page=" + answered.page', self.block)

    def test_section_is_mounted_on_load(self):
        self.assertIn("renderAnsweredAsks();", self.source)
        html = (_WEB_DIR / "index.html").read_text()
        self.assertIn('<section id="answered-asks"', html)
