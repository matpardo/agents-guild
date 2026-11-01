import contextlib
import io
import unittest
from unittest import mock

from guild import cli
from guild.errors import GuildError


def _help_text(parser, name):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        parser.parse_args([name, "--help"])
    return out.getvalue()


class LazyParserTest(unittest.TestCase):
    def test_known_command_builds_only_its_own_builder(self):
        unrelated = mock.Mock(side_effect=AssertionError("unrelated builder called"))
        with mock.patch.dict(cli._COMMAND_BUILDERS, {"ideas": unrelated}):
            parser = cli._build_parser_for(["whoami"])
        self.assertEqual("whoami", parser.parse_args(["whoami"]).command)
        unrelated.assert_not_called()

    def test_main_does_not_build_the_full_parser_for_a_known_command(self):
        stop = GuildError("stop here", 1)
        with (
            mock.patch("guild.cli.build_parser", side_effect=AssertionError("full parser built")),
            mock.patch("guild.cli._build_context", side_effect=stop),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(1, cli.main(["whoami"]))

    def test_help_lists_every_top_level_command(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            cli.main(["--help"])
        self.assertEqual(0, raised.exception.code)
        for name in cli._COMMAND_BUILDERS:
            self.assertIn(name, out.getvalue())

    def test_unknown_command_exits_2_with_invalid_choice(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            cli.main(["nonsense"])
        self.assertEqual(2, raised.exception.code)
        self.assertIn("invalid choice", err.getvalue())

    def test_every_command_help_matches_the_full_parser(self):
        full = cli.build_parser()
        for name in cli._COMMAND_BUILDERS:
            with self.subTest(command=name):
                self.assertEqual(_help_text(full, name), _help_text(cli._build_parser_for([name]), name))

    def test_builders_cover_every_command_of_the_full_parser(self):
        full = cli.build_parser()
        registered = next(a for a in full._actions if a.dest == "command").choices
        self.assertEqual(list(registered), list(cli._COMMAND_BUILDERS))
