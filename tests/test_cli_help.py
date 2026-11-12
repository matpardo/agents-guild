import argparse
import contextlib
import io
import unittest

from guild import pii
from guild.cli import build_parser


def _missing_help(parser, path):
    missing = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for choice in action._choices_actions:
            if not choice.help:
                missing.append(path + [choice.dest])
        for name, sub in action.choices.items():
            missing.extend(_missing_help(sub, path + [name]))
    return missing


class CliHelpTest(unittest.TestCase):
    def test_every_subparser_has_help(self):
        self.assertEqual([], _missing_help(build_parser(), []))

    def test_top_level_help_describes_key_commands(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            build_parser().parse_args(["--help"])
        text = " ".join(out.getvalue().split())
        for expected in (
            "show the next action for your party",
            "read-only: PRs in the order to merge by hand",
            "track PRs and set their state",
            "relaunch active parties and stopped adventurers after a reboot",
            "serve the local board in a browser",
            "see docs/commands.md",
        ):
            self.assertIn(expected.lower(), text.lower())

    def test_ask_help_states_length_limits(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            build_parser().parse_args(["ask", "--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("at most {} characters".format(pii.ASK_QUESTION_MAX_LENGTH), text)
        self.assertIn("at most {} characters".format(pii.ASK_CONTEXT_MAX_LENGTH), text)


if __name__ == "__main__":
    unittest.main()
