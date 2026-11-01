import unittest

from guild import ask_legibility
from guild.commands import board


class JargonCountTests(unittest.TestCase):
    def test_each_token_kind_counts(self):
        for text in (
            "a/b/c",
            "guild/commands/ask.py",
            "foo.py",
            "see #123",
            "task T05",
            "card PROJ-12",
            "commit abc1234",
            "run `x`",
            "my_ident",
        ):
            self.assertEqual(ask_legibility.jargon_count(text), 1, text)

    def test_plain_words_and_numbers_count_zero(self):
        for text in ("and/or", "y/o", "cliente/servidor", "1234567", "guild/foo"):
            self.assertEqual(ask_legibility.jargon_count(text), 0, text)

    def test_plain_text_counts_zero(self):
        self.assertEqual(ask_legibility.jargon_count("Should we ship this change today?"), 0)
        self.assertEqual(ask_legibility.jargon_count("¿Publicamos el cambio hoy?"), 0)


class WarningLinesTests(unittest.TestCase):
    def test_clean_ask_has_no_warning(self):
        self.assertEqual(ask_legibility.warning_lines("Ship it?", "Tests pass."), [])

    def test_question_at_the_limit_does_not_warn(self):
        self.assertEqual(ask_legibility.warning_lines("T01 and T02?", "ctx"), [])

    def test_question_over_the_limit_warns(self):
        lines = ask_legibility.warning_lines("T01 T02 T03?", "ctx")
        self.assertEqual(lines[0], "warning: question carries 3 ids or paths")
        self.assertEqual(len(lines), 2)

    def test_context_over_the_limit_warns(self):
        lines = ask_legibility.warning_lines("Ship?", " ".join("T0{}".format(n) for n in range(1, 8)))
        self.assertEqual(lines[0], "warning: context carries 7 ids or paths")


class AskTextLinesTests(unittest.TestCase):
    _STYLES = (lambda inner: "[{}]".format(inner), lambda inner: "<{}>".format(inner))

    def _lines(self, text, styles):
        return ask_legibility.ask_text_lines(text, "  ", 40, styles)

    def test_paragraphs_and_breaks_are_kept(self):
        self.assertEqual(self._lines("one\ntwo\n\nthree", None), ["  one", "  two", "", "  three"])

    def test_bold_and_plain_segments_are_styled(self):
        self.assertEqual(self._lines("a **b** c", self._STYLES), ["  [a ]<b>[ c]"])

    def test_bold_stays_literal_without_styles(self):
        self.assertEqual(self._lines("a **b** c", None), ["  a **b** c"])

    def test_unclosed_bold_stays_literal_but_plain_styled(self):
        self.assertEqual(self._lines("a **b c", self._STYLES), ["  [a **b c]"])

    def test_bold_spanning_a_wrap_is_styled_on_both_lines(self):
        lines = self._lines("start **this bold text spans the wrap boundary** end", self._STYLES)
        self.assertEqual(
            lines,
            ["  [start ]<this bold text spans the wrap>", "  <boundary>[ end]"],
        )

    def test_blank_lines_stay_empty_with_styles(self):
        self.assertEqual(self._lines("a\n\nb", self._STYLES), ["  [a]", "", "  [b]"])

    def test_control_sequences_are_stripped(self):
        self.assertEqual(self._lines("a\x1b[31mb", None), ["  ab"])


class BoardAskTextStyleTests(unittest.TestCase):
    def test_context_is_dimmed_and_recommend_is_not(self):
        painter = board._Painter(True, 60)
        dimmed = board._ask_text_lines(painter, "plain **bold**", lambda inner: painter.paint(inner, "dim"))
        plain = board._ask_text_lines(painter, "plain **bold**", str)
        self.assertEqual(dimmed, ["       \x1b[2mplain \x1b[0m\x1b[1mbold\x1b[0m"])
        self.assertEqual(plain, ["       plain \x1b[1mbold\x1b[0m"])
