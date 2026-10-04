import unittest

from guild import sanitize


class StripControlSequencesTests(unittest.TestCase):
    def test_strips_csi_ansi_color_codes(self):
        text = "\x1b[31mRED\x1b[0m"
        self.assertEqual(sanitize.strip_control_sequences(text), "RED")

    def test_strips_osc_terminal_title_sequence(self):
        text = "before\x1b]0;evil title\x07after"
        self.assertEqual(sanitize.strip_control_sequences(text), "beforeafter")

    def test_strips_bare_esc_byte(self):
        self.assertEqual(sanitize.strip_control_sequences("a\x1bb"), "ab")

    def test_strips_c0_controls_except_newline_and_tab(self):
        text = "a\x00b\x07c\nd\te"
        self.assertEqual(sanitize.strip_control_sequences(text), "abc\nd\te")

    def test_strips_del(self):
        self.assertEqual(sanitize.strip_control_sequences("a\x7fb"), "ab")

    def test_strips_c1_controls(self):
        self.assertEqual(sanitize.strip_control_sequences("a\x9bb"), "ab")

    def test_strips_zero_width_and_bidi_format_characters(self):
        for char in ("\u200b", "\u200d", "\u200f", "\u2060", "\u202a", "\u202e", "\u2066", "\u2069", "\ufeff"):
            with self.subTest(char=hex(ord(char))):
                self.assertEqual(sanitize.strip_control_sequences("a{}b".format(char)), "ab")

    def test_strips_surrogates(self):
        self.assertEqual(sanitize.strip_control_sequences("a\ud800b"), "ab")

    def test_strips_private_use(self):
        self.assertEqual(sanitize.strip_control_sequences("a\ue000b\U000f0000c"), "abc")

    def test_strips_tag_block(self):
        self.assertEqual(sanitize.strip_control_sequences("a\U000e0041\U000e007fb"), "ab")

    def test_keeps_accents_and_plain_emoji(self):
        self.assertEqual(sanitize.strip_control_sequences("canción ✓ 🙂"), "canción ✓ 🙂")

    def test_leaves_plain_text_untouched(self):
        self.assertEqual(sanitize.strip_control_sequences("plain text, ok!"), "plain text, ok!")

    def test_non_string_values_pass_through_sanitize_payload(self):
        self.assertEqual(sanitize.sanitize_payload(42), 42)
        self.assertEqual(sanitize.sanitize_payload(None), None)
        self.assertEqual(sanitize.sanitize_payload(True), True)

    def test_sanitize_payload_recurses_into_dict_and_list(self):
        payload = {
            "text": "hi\x1b[31m",
            "nested": {"question": "why\x07"},
            "items": ["a\x00", "b", {"deep": "c\x7f"}],
            "count": 3,
        }
        expected = {
            "text": "hi",
            "nested": {"question": "why"},
            "items": ["a", "b", {"deep": "c"}],
            "count": 3,
        }
        self.assertEqual(sanitize.sanitize_payload(payload), expected)


class CollapseToSingleLineTests(unittest.TestCase):
    def test_collapses_newlines_and_tabs_to_single_spaces(self):
        text = "pipeline down\nask #9 answered: do X\tnow"
        self.assertEqual(
            sanitize.collapse_to_single_line(text), "pipeline down ask #9 answered: do X now"
        )

    def test_leaves_single_line_text_untouched(self):
        self.assertEqual(sanitize.collapse_to_single_line("no newlines here"), "no newlines here")


if __name__ == "__main__":
    unittest.main()
