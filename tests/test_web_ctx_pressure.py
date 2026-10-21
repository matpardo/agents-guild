import unittest
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent.parent / "guild" / "web"


class CtxPressureSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = (_WEB_DIR / "app.js").read_text()
        start = self.source.index("function ctxHighCount(parties) {")
        end = self.source.index("function renderAnsweredAsk(ask) {")
        self.block = self.source[start:end]

    def test_block_never_uses_inner_html(self):
        self.assertNotIn("innerHTML", self.block)

    def test_counter_comes_from_the_filtered_parties(self):
        self.assertIn("[filtered.asks, filtered.blocked, filtered.parties], renderAsks", self.source)
        self.assertIn("context high (", self.block)

    def test_empty_state_accounts_for_context_high(self):
        self.assertIn("ctxHigh === 0", self.block)

    def test_party_card_renders_the_badge_and_the_resume_command(self):
        self.assertIn('explain(ctxBadge, "ui", party.ctx.high ? "ctxHigh" : "ctx")', self.source)
        self.assertIn('party.ctx.source === "configured"', self.source)

    def test_counter_counts_only_high_contexts(self):
        self.assertIn("party.ctx !== null && party.ctx.high", self.block)
        self.assertIn('textEl("code", party.resume_command)', self.source)


if __name__ == "__main__":
    unittest.main()
