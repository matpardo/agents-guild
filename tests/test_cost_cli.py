from datetime import timedelta

from guild import db, events, timeutil
from guild.cli import _build_context
from tests.testutil import GuildTestCase
from tests.transcript_fixtures import assistant_line, write_transcript

_OPUS = "claude-opus-4-1"
_SONNET = "claude-sonnet-4-5"


def _stamp(moment):
    return moment.isoformat().replace("+00:00", "Z")


class CostCliTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.other_dir = self.register_project("zeta", ["zeta/app"])
        self.now = timeutil.utcnow()
        self.recent = _stamp(self.now - timedelta(hours=1))
        self.older = _stamp(self.now - timedelta(days=3))

    def _transcript(self, session_id, lines):
        write_transcript(self.claude_projects_dir / "dir-a" / (session_id + ".jsonl"), lines)

    def _cost(self, *args):
        return self.run_cli(["cost"] + list(args), None, self.root)

    def _rows(self, stdout):
        return [line.split() for line in stdout.splitlines()]

    def _seed(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "qa", "--title", "qa"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "qa", "T01", "--title", "t"], "sess-1", self.repo_dir)
        ctx = _build_context("sess-1", self.root)
        with db.writing(ctx.conn):
            events.record(
                ctx.conn,
                self.now - timedelta(hours=2),
                ctx.origin,
                "alpha",
                "sess-1",
                "acme",
                "task.started",
                "local",
                {"quest": "qa", "tid": "T01", "summary": "s"},
            )
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.other_dir)
        self._transcript(
            "sess-1",
            [
                assistant_line("m1", self.recent, _OPUS, 1000, 2000, 3000, 100),
                assistant_line("m1", self.recent, _OPUS, 1000, 2000, 3000, 400),
                assistant_line("m2", self.recent, _SONNET, 10, 20, 30, 40),
            ],
        )
        self._transcript("sess-2", [assistant_line("m3", self.recent, _OPUS, 5, 0, 0, 5)])
        self._transcript("sess-3", [assistant_line("m4", self.recent, _OPUS, 7, 0, 0, 1)])

    def test_session_totals_match_manual_sum_with_dedupe(self):
        self._seed()
        code, stdout, _ = self._cost("--by", "session")
        self.assertEqual(code, 0)
        rows = self._rows(stdout)
        self.assertEqual(rows[0], ["session", "input", "cache", "write", "cache", "read", "output"])
        by_key = {row[0]: row[1:] for row in rows[1:]}
        self.assertEqual(by_key["sess-1"], ["0.001", "0.002", "0.003", "0.000"])
        self.assertEqual(rows[-1][0], "total")

    def test_totals_are_in_million_tokens(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self._transcript("sess-1", [assistant_line("m1", self.recent, _OPUS, 1500000, 0, 2500000, 500000)])
        _, stdout, _ = self._cost("--by", "party")
        self.assertEqual(self._rows(stdout)[1], ["alpha", "1.500", "0.000", "2.500", "0.500"])

    def test_by_party_shows_unbound(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "party")
        keys = [row[0] for row in self._rows(stdout)[1:]]
        self.assertEqual(sorted(keys), ["alpha", "beta", "total", "unbound"])

    def test_by_model(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "model")
        keys = [row[0] for row in self._rows(stdout)[1:]]
        self.assertEqual(sorted(keys), [_OPUS, _SONNET, "total"])

    def test_by_quest_uses_dash_for_none(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "quest")
        keys = [row[0] for row in self._rows(stdout)[1:]]
        self.assertEqual(sorted(keys), ["-", "qa", "total"])

    def test_by_task_joins_quest_and_tid(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "task")
        keys = [row[0] for row in self._rows(stdout)[1:]]
        self.assertEqual(sorted(keys), ["-", "qa/T01", "total"])

    def test_project_filter_excludes_unbound_and_other_projects(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "party", "--project", "acme")
        keys = [row[0] for row in self._rows(stdout)[1:]]
        self.assertEqual(keys, ["alpha", "total"])

    def test_since_excludes_older_days(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self._transcript(
            "sess-1",
            [
                assistant_line("m1", self.older, _OPUS, 1000000, 0, 0, 0),
                assistant_line("m2", self.recent, _OPUS, 2000000, 0, 0, 0),
            ],
        )
        _, everything, _ = self._cost("--by", "party")
        _, recent_only, _ = self._cost("--by", "party", "--since", "1d")
        self.assertEqual(self._rows(everything)[1][1], "3.000")
        self.assertEqual(self._rows(recent_only)[1][1], "2.000")

    def test_invalid_since_fails(self):
        code, _, stderr = self._cost("--since", "soon")
        self.assertEqual(code, 1)
        self.assertIn("invalid duration", stderr)

    def test_empty_prints_no_cost_data(self):
        code, stdout, _ = self._cost()
        self.assertEqual(code, 0)
        self.assertEqual(stdout.strip(), "no cost data")

    def test_alignment_and_total_row(self):
        self._seed()
        _, stdout, _ = self._cost("--by", "party")
        lines = stdout.splitlines()
        self.assertEqual(len({len(line) for line in lines}), 1)
        total = lines[-1].split()
        self.assertEqual(total[0], "total")
        self.assertEqual(total[1:], ["0.001", "0.002", "0.003", "0.000"])
