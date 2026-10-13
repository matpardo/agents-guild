import json

from guild import db, dispatch_launch, dispatch_rules, events
from guild.cli import _build_context
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase

PROMPT = "Continue the work described in the guild brief. Dispatched: ask #12 was answered; read guild asks 12."


class LaunchBase(GuildTestCase):
    notify = {"command": ["notify-send", "guild"]}

    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.other_dir = self.root / "elsewhere"
        self.other_dir.mkdir()
        self.write_block()
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.tmux = FakeTmux(True, True, {}, 0)
        self.pushes = []

    def write_block(self):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {
            "rules": {"ask_answered": "on"},
        }
        data["notify"] = self.notify
        path.write_text(json.dumps(data))

    def ctx(self):
        ctx = _build_context(None, self.repo_dir)
        self.addCleanup(ctx.conn.close)
        return ctx

    def project_config(self):
        return json.loads((self.config_home / "guild" / "projects" / "acme.json").read_text())

    def trigger(self, number, party):
        return dispatch_rules.Trigger(
            "acme",
            "ask_answered",
            "ask_answered:{}".format(number),
            party,
            "ask #{}".format(number),
            PROMPT,
        )

    def decide(self, trigger, mode):
        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, self.pushes.append)
        return launcher.decide(self.project_config(), trigger, mode)

    def preview(self, trigger, mode):
        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, self.pushes.append)
        return launcher.preview(self.project_config(), trigger, mode)

    def record(self, kind, party, payload, now):
        ctx = self.ctx()
        with db.writing(ctx.conn):
            events.record(ctx.conn, now, ctx.origin, party, None, "acme", kind, "local", payload)

    def kinds(self):
        rows = self.ctx().conn.execute(
            "SELECT kind FROM events WHERE kind LIKE 'dispatch.%' OR kind = 'leader.window_launched' ORDER BY seq"
        ).fetchall()
        return [row["kind"] for row in rows]

    def decisions(self):
        rows = self.ctx().conn.execute("SELECT * FROM dispatch_decisions ORDER BY key, mode").fetchall()
        return [dict(row) for row in rows]

    def notices(self):
        rows = self.ctx().conn.execute("SELECT * FROM notices ORDER BY id").fetchall()
        return [dict(row) for row in rows]
