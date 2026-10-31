import contextlib
import io
import sys
from unittest import mock

from guild import cli
from tests.testutil import GuildTestCase


class HookFastPathTests(GuildTestCase):
    def _run(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("")):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_hook_runs_without_building_the_full_parser(self):
        with mock.patch.object(cli, "build_parser", side_effect=AssertionError("full parser built")):
            code, out, err = self._run(["hook", "pre-answer"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")

    def test_unknown_hook_name_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as raised:
            self._run(["hook", "no-such-hook"])
        self.assertEqual(raised.exception.code, 2)

    def test_full_parser_accepts_every_hook_name(self):
        parser = cli.build_parser()
        for name in cli.HOOK_NAMES:
            self.assertEqual(parser.parse_args(["hook", name]).hook_name, name)
