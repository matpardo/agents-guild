import unittest

from guild.resources import sizes


class ParseHumanSizeTests(unittest.TestCase):
    def test_units_are_decimal(self):
        cases = {
            "0B": 0,
            "512B": 512,
            "18.49kB": 18490,
            "21.7MB": 21700000,
            "2.29GB": 2290000000,
            "1.5TB": 1500000000000,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(sizes.parse_human_size(text), expected)

    def test_only_first_token_counts_so_virtual_suffix_is_ignored(self):
        self.assertEqual(sizes.parse_human_size("21.7MB (virtual 1.74GB)"), 21700000)

    def test_not_available_is_none(self):
        self.assertIsNone(sizes.parse_human_size("N/A"))

    def test_garbage_is_none(self):
        for text in ("", "   ", "lots", "12XB", "GB", "1.2.3GB", None):
            with self.subTest(text=text):
                self.assertIsNone(sizes.parse_human_size(text))


class ParseDuOutputTests(unittest.TestCase):
    def test_first_tab_token_is_the_byte_count(self):
        self.assertEqual(sizes.parse_du_output("4096\t/home/u/acme/app\n"), 4096)

    def test_path_with_spaces_and_brackets(self):
        self.assertEqual(sizes.parse_du_output("77\t/home/u/my app [x]\n"), 77)

    def test_last_line_wins_when_du_prints_several(self):
        self.assertEqual(sizes.parse_du_output("1\t/a/b\n99\t/a\n"), 99)

    def test_empty_or_garbage_is_none(self):
        for text in ("", "\n", "not a number\t/a\n", "12 /a\n"):
            with self.subTest(text=text):
                self.assertIsNone(sizes.parse_du_output(text))


if __name__ == "__main__":
    unittest.main()
