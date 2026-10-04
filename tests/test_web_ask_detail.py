import json
import unittest
from pathlib import Path

from tests.test_web_server import WebServerTestCase

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


class AskDetailEndpointTests(WebServerTestCase):
    def setUp(self):
        super().setUp()
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(
            ["ask", "Which?", "--context", "ctx", "--ref", "task:demo/T01"], "sess-1", repo_dir
        )
        self.host = "127.0.0.1:{}".format(self.port)

    def test_returns_detail_shape(self):
        response, body = self._get("/api/asks/1", self.host)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        model = json.loads(body)
        self.assertEqual(
            set(model),
            {
                "id", "party", "state", "question", "context", "options", "created_at", "created",
                "answer", "answered_at", "answered", "refs", "origin", "resume", "events",
            },
        )
        self.assertEqual((model["id"], model["party"], model["state"]), (1, "alpha", "open"))
        self.assertEqual(model["refs"][0]["kind"], "task")
        self.assertEqual(model["origin"]["session_id"], "sess-1")

    def test_unknown_ask_is_404_json(self):
        response, body = self._get("/api/asks/42", self.host)
        self.assertEqual(response.status, 404)
        self.assertEqual(json.loads(body), {"error": "unknown ask #42"})

    def test_non_numeric_id_is_404(self):
        response, body = self._get("/api/asks/abc", self.host)
        self.assertEqual(response.status, 404)

    def test_wrong_host_is_rejected_like_the_board(self):
        response, body = self._get("/api/asks/1", "evil.example")
        self.assertEqual(response.status, 421)

    def test_post_is_405(self):
        conn = self._connection()
        conn.request("POST", "/api/asks/1", body="{}", headers={"Host": self.host, "Content-Type": "application/json"})
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 405)

    def test_answered_ask_carries_answer(self):
        self.run_cli(["answer", "1", "five"], None, None)
        response, body = self._get("/api/asks/1", self.host)
        model = json.loads(body)
        self.assertEqual((model["state"], model["answer"]), ("answered", "five"))
        self.assertIsNotNone(model["answered_at"])


class AskDetailControlSourceTests(unittest.TestCase):
    def setUp(self):
        source = (_WEB_DIR / "app.js").read_text()
        start = source.index("var askDetails =")
        end = source.index("function renderAsk(ask) {")
        self.block = source[start:end]
        self.source = source

    def test_block_never_uses_inner_html(self):
        self.assertNotIn("innerHTML", self.block)

    def test_labels_all_go_through_the_titled_helper(self):
        self.assertNotIn("textEl(", self.block.replace("var node = textEl(tag, value);", ""))
        self.assertIn("node.title = tooltip;", self.block)
        self.assertIn("anchor.title = tooltip;", self.block)

    def test_links_only_for_https_urls(self):
        self.assertIn('url.indexOf("https://") !== 0', self.block)
        self.assertNotIn("link(ref.url", self.block.replace("detailLink(ref.url", ""))

    def test_render_ask_mounts_the_control(self):
        self.assertIn("article.appendChild(renderAskDetailControl(ask));", self.source)

    def test_detail_is_fetched_from_the_ask_endpoint(self):
        self.assertIn('"/api/asks/" + askId', self.block)
