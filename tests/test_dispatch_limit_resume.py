import json
import os
import time

from guild import db, events
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase
from tests.transcript_fixtures import append_transcript, assistant_line, write_transcript

_NOTIFIED = "acme: limit_resume {} -> notified alpha"


def _limit_line(resets_at):
    return json.dumps(
        {
            "type": "assistant",
            "isApiErrorMessage": True,
            "error": "rate_limit",
            "apiErrorStatus": 429,
            "quotaLimits": {"status": "rejected", "resetsAt": resets_at, "rateLimitType": "five_hour"},
            "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "limit"}]},
        }
    )


class LimitResumeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.write_block({"limit_resume": "on"})
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.transcript = self.claude_projects_dir / "p" / "sess-1.jsonl"
        self.tmux = FakeTmux(True, True, {"@5": "alpha"}, 0)
        self.pushes = []
        self.record_window("@5")
        self.run_pass()
        self.past = int(time.time()) - 120
        write_transcript(self.transcript, [_limit_line(self.past)])

    def write_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"rules": rules}
        data["notify"] = {"command": ["notify-send", "guild"]}
        path.write_text(json.dumps(data))

    def record_window(self, window_id):
        ctx = _build_context(None, self.repo_dir)
        try:
            with db.writing(ctx.conn):
                events.record(
                    ctx.conn, ctx.now, ctx.origin, "alpha", None, "acme", "leader.window_launched", "local",
                    {"party": "alpha", "generation": 1, "window_id": window_id},
                )
        finally:
            ctx.conn.close()

    def run_pass(self, dry_run=False):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, dry_run, self.tmux, self.pushes.append)
        finally:
            ctx.conn.close()

    def sends(self):
        return [call for call in self.tmux.calls if call[0] == "send-keys"]

    def notices(self):
        code, out, err = self.run_cli(["notices"], "sess-1", self.repo_dir)
        return [line for line in out.splitlines() if "resume alpha by hand" in line]

    def test_notifies_once_after_the_reset_and_never_types_into_the_window(self):
        self.assertEqual(self.run_pass(), [_NOTIFIED.format(self.past)])
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "limit-reset"]])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.sends(), [])
        self.assertEqual(len(self.notices()), 1)

    def test_nothing_before_the_grace_after_the_reset(self):
        write_transcript(self.transcript, [_limit_line(int(time.time()) - 30)])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.sends(), [])

    def test_a_new_limit_hit_notifies_again(self):
        self.run_pass()
        append_transcript(self.transcript, [_limit_line(self.past + 10)])
        self.assertEqual(self.run_pass(), [_NOTIFIED.format(self.past + 10)])

    def test_later_normal_line_means_nothing(self):
        append_transcript(self.transcript, [assistant_line("m1", "2026-10-11T00:00:00Z", "claude", 1, 0, 0, 1)])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_malformed_last_line_means_nothing(self):
        write_transcript(self.transcript, ["{not json", _limit_line(self.past).replace(str(self.past), '"soon"')])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_party_without_live_session_means_nothing(self):
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_dry_run_notifies_nothing(self):
        self.assertEqual(self.run_pass(True), ["acme: limit_resume {} -> would notify alpha".format(self.past)])
        self.assertEqual(self.sends(), [])

    def test_dry_run_mode_records_a_plan_only(self):
        self.write_block({"limit_resume": "dry-run"})
        self.assertEqual(self.run_pass(), ["acme: limit_resume {} -> planned: notify alpha".format(self.past)])
        self.assertEqual(self.sends(), [])
        self.assertEqual(self.notices(), [])

    def test_rule_absent_means_nothing(self):
        self.write_block({})
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
