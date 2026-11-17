import json
import re
import sqlite3
import unittest

from guild import ask_share

_TRACE_RE = re.compile(r"guild|ask #[0-9]|notice #[0-9]|idea #[0-9]|adventurer [0-9]", re.IGNORECASE)


def _row(**overrides):
    values = {
        "question": "Ship now?",
        "context": "First line\nsecond line\n\nNew <script>paragraph",
        "options": json.dumps(["yes", "no & wait"]),
        "recommend": "yes, it is safe",
        "answer": None,
    }
    values.update(overrides)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    columns = ", ".join("? AS {}".format(name) for name in values)
    return conn.execute("SELECT " + columns, list(values.values())).fetchone()


class AskShareTextTests(unittest.TestCase):
    def test_text_lists_every_section(self):
        row = _row(answer="go")
        self.assertEqual(
            ask_share.text(row),
            "**Ship now?**\n\nContext:\nFirst line\nsecond line\n\nNew <script>paragraph\n\n"
            "Options:\n- yes\n- no & wait\n\nRecommendation:\nyes, it is safe\n\nAnswer:\ngo",
        )

    def test_text_omits_empty_sections(self):
        text = ask_share.text(_row(context="", options="[]", recommend=None))
        self.assertEqual(text, "**Ship now?**")

    def test_question_bold_markers_do_not_nest(self):
        row = _row(question="Pick **db** now?")
        self.assertTrue(ask_share.text(row).startswith("**Pick db now?**"))
        self.assertTrue(ask_share.html(row).startswith("<p><strong>Pick db now?</strong></p>"))


class AskShareHtmlTests(unittest.TestCase):
    def test_html_escapes_and_formats(self):
        html = ask_share.html(_row())
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("<p><strong>Ship now?</strong></p>", html)
        self.assertIn("<p>First line<br>second line</p><p>New &lt;script&gt;paragraph</p>", html)
        self.assertIn("<ul><li>yes</li><li>no &amp; wait</li></ul>", html)
        self.assertIn("<p><strong>Recommendation:</strong></p><p>yes, it is safe</p>", html)
        self.assertNotIn("Answer", html)

    def test_unclosed_bold_stays_literal(self):
        self.assertIn("<p>a **b</p>", ask_share.html(_row(context="a **b")))

    def test_html_omits_empty_sections(self):
        html = ask_share.html(_row(context="", options="[]", recommend=None))
        self.assertEqual(html, "<p><strong>Ship now?</strong></p>")

    def test_share_has_no_traces(self):
        row = _row(answer="go")
        self.assertIsNone(_TRACE_RE.search(ask_share.text(row)))
        self.assertIsNone(_TRACE_RE.search(ask_share.html(row)))


if __name__ == "__main__":
    unittest.main()
