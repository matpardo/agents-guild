import sys
from datetime import timedelta

from guild import db, events, session_info, timeutil, tmux_windows
from guild.adapters import github
from guild.commands import dispatch_pause as dispatch_pause_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands

_DUPLICATE = "duplicate"
_BUSY = "busy"
_SKIP = "skip"
_PLAN = "plan"
_SUGGEST = "suggest"
_DRY_RUN_MODE = "dry-run"
_REAL_MODE = "on"
_HANDED_OFF_STATE = "awaiting-leader"
_CLOSED_STATE = "closed"
_NOTICE_TTL = "12h"
_FAILURE_WAIT = "dispatch-failed"
_ANNOUNCE_WAITS = {"merge_head": "merge-head", "sdd_progress": "sdd-progress", "limit_resume": "limit-reset"}
_SUGGEST_WAIT = "ready"
_PROMOTE_WAIT = "pr-promote"
_DEFER_DEADLINE = timedelta(hours=24)
_DEFERRED_TOO_LONG = "deferred too long"


class _Notice:
    def __init__(self, text, announces):
        self.text = text
        self.announces = announces


class Verdict:
    def __init__(self, kind, reason, notice, generation):
        self.kind = kind
        self.reason = reason
        self.notice = notice
        self.generation = generation


def _verdict_without_suggestion(kind, reason, notice, generation):
    return Verdict(kind, reason, notice, generation)


class Launcher:
    def __init__(self, ctx, tmux, push_runner):
        self._ctx = ctx
        self._tmux = tmux
        self._push_runner = push_runner

    def decide(self, project_config, trigger, mode):
        try:
            verdict = self.evaluate(project_config, trigger, mode)
            return self._execute(project_config, trigger, mode, verdict)
        except Exception as error:
            return self._record_error(trigger, mode, error)

    def announce(self, project_config, trigger, mode):
        if self._paused():
            return None
        try:
            return self._announce(project_config, trigger, mode)
        except Exception as error:
            return self._record_error(trigger, mode, error)

    def preview_announce(self, trigger, mode):
        if self._paused():
            return None
        if self._already_decided(trigger, mode):
            return None
        return "{}would notify {}".format(self._prefix(trigger), trigger.party)

    def promote(self, project_config, trigger, mode):
        if self._paused():
            return None
        try:
            return self._promote(project_config, trigger, mode)
        except Exception as error:
            return self._record_error(trigger, mode, error)

    def preview_promote(self, trigger, mode):
        if self._paused():
            return None
        if self._already_decided(trigger, mode):
            return None
        verb = "notify" if trigger.needs_human_review else "promote"
        return "{}would {} {}".format(self._prefix(trigger), verb, trigger.party)

    def _promote(self, project_config, trigger, mode):
        if self._already_decided(trigger, mode):
            return None
        prefix = self._prefix(trigger)
        verb = "notify" if trigger.needs_human_review else "promote"
        if mode == _DRY_RUN_MODE:
            self._record_decided(trigger, mode, "planned", None, None)
            return "{}planned: {} {}".format(prefix, verb, trigger.party)
        if not trigger.needs_human_review:
            try:
                github.pr_ready(self._ctx.cwd, trigger.repo, trigger.number)
            except github.GhCommandError as error:
                return self._promote_failure(project_config, trigger, mode, str(error))
        outcome = "notified" if trigger.needs_human_review else "promoted"
        self._record_decided(trigger, mode, outcome, None, None)
        announces = "dispatch:{}:{}:{}".format(trigger.project, trigger.key, outcome)
        self._post_notice(trigger.project, _Notice(trigger.prompt, announces))
        self._push(project_config, trigger.party, _PROMOTE_WAIT)
        return "{}{} {}".format(prefix, outcome, trigger.party)

    def _promote_failure(self, project_config, trigger, mode, reason):
        self._record_decided(trigger, mode, "failed", None, reason)
        text = "dispatch could not mark {} ready: {}".format(trigger.subject, reason)
        announces = "dispatch:{}:{}:failed".format(trigger.project, trigger.key)
        self._post_notice(trigger.project, _Notice(text, announces))
        self._push(project_config, trigger.party, _FAILURE_WAIT)
        return "{}failed {}: {}".format(self._prefix(trigger), trigger.party, reason)

    def _announce(self, project_config, trigger, mode):
        if self._already_decided(trigger, mode):
            return None
        prefix = self._prefix(trigger)
        if mode == _DRY_RUN_MODE:
            self._record_decided(trigger, mode, "planned", None, None)
            return "{}planned: notify {}".format(prefix, trigger.party)
        self._record_decided(trigger, mode, "notified", None, None)
        announces = "dispatch:{}:{}:notified".format(trigger.project, trigger.key)
        self._post_notice(trigger.project, _Notice(trigger.prompt, announces))
        self._push(project_config, trigger.party, _ANNOUNCE_WAITS[trigger.rule])
        return "{}notified {}".format(prefix, trigger.party)

    def preview(self, project_config, trigger, mode):
        verdict = self.evaluate(project_config, trigger, mode)
        if verdict.kind == _DUPLICATE:
            return None
        prefix = self._prefix(trigger)
        if verdict.kind == _BUSY:
            return "{}would defer {}: {}".format(prefix, trigger.party, verdict.reason)
        if verdict.kind == _SKIP:
            return "{}would skip {}: {}".format(prefix, trigger.party, verdict.reason)
        return "{}would suggest revive {} g{}".format(prefix, trigger.party, verdict.generation)

    def evaluate(self, project_config, trigger, mode):
        if self._already_decided(trigger, mode):
            return _verdict_without_suggestion(_DUPLICATE, None, None, None)
        party = self._ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (trigger.party,)).fetchone()
        verdict = self._standing(trigger, party)
        if verdict is not None:
            return verdict
        kind = _PLAN if mode == _DRY_RUN_MODE else _SUGGEST
        return Verdict(kind, None, None, party["generation"] + 1)

    def _prefix(self, trigger):
        return "{}: {} {} -> ".format(trigger.project, trigger.rule, trigger.subject)

    def _already_decided(self, trigger, mode):
        rows = self._ctx.conn.execute(
            "SELECT mode FROM dispatch_decisions WHERE project = ? AND key = ? AND outcome != 'deferred'",
            (trigger.project, trigger.key),
        ).fetchall()
        if mode == _REAL_MODE:
            return any(row["mode"] == _REAL_MODE for row in rows)
        return bool(rows)

    def _standing(self, trigger, party):
        if party is None or party["state"] == _CLOSED_STATE:
            generation = None if party is None else party["generation"] + 1
            return _verdict_without_suggestion(_SKIP, "party closed", None, generation)
        generation = party["generation"] + 1
        if party["keeper"]:
            return _verdict_without_suggestion(_SKIP, "keeper", None, generation)
        busy_reason = self._busy_reason(trigger, party)
        if busy_reason is not None:
            return _verdict_without_suggestion(_BUSY, busy_reason, None, generation)
        if party["state"] != _HANDED_OFF_STATE:
            text = "dispatch skipped for {}: it did not hand off; run guild revive --party {}".format(
                trigger.party, trigger.party
            )
            notice = _Notice(text, "dispatch:{}:{}:skipped".format(trigger.project, trigger.key))
            return _verdict_without_suggestion(_SKIP, "party not handed off", notice, generation)
        return None

    def _paused(self):
        return dispatch_pause_commands.current(self._ctx.conn) is not None

    def _busy_reason(self, trigger, party):
        conn, ctx = self._ctx.conn, self._ctx
        if self._paused():
            return "dispatch paused"
        if party["leader_session_id"] in session_info.live_session_ids(ctx.sessions_dir):
            return "live session"
        if self._tmux.installed() and trigger.party in tmux_windows.window_names(self._tmux):
            return "open window"
        paused = raid_commands.paused_member_raids(conn, ctx.now, trigger.party)
        if paused:
            return "raid {} paused".format(paused[0]["raid"])
        return None

    def _execute(self, project_config, trigger, mode, verdict):
        if verdict.kind == _DUPLICATE:
            return None
        prefix = self._prefix(trigger)
        if verdict.kind == _BUSY:
            return self._defer(trigger, mode, verdict)
        if verdict.kind == _SKIP:
            self._record_decided(trigger, mode, "skipped", verdict.generation, verdict.reason)
            if verdict.notice is not None:
                self._post_notice(trigger.project, verdict.notice)
            return "{}skipped {}: {}".format(prefix, trigger.party, verdict.reason)
        if verdict.kind == _PLAN:
            self._record_decided(trigger, mode, "planned", verdict.generation, None)
            return "{}planned: suggest revive {} g{} ({})".format(prefix, trigger.party, verdict.generation, mode)
        return self._suggest(project_config, trigger, mode, verdict)

    def _suggest(self, project_config, trigger, mode, verdict):
        self._record_decided(trigger, mode, "suggested", verdict.generation, None)
        text = "{} ready to resume ({} {}): run guild revive --party {}".format(
            trigger.party, trigger.rule, trigger.subject, trigger.party
        )
        announces = "dispatch:{}:{}:suggested".format(trigger.project, trigger.key)
        self._post_notice(trigger.project, _Notice(text, announces))
        self._push(project_config, trigger.party, _SUGGEST_WAIT)
        return "{}suggested revive {} g{}".format(self._prefix(trigger), trigger.party, verdict.generation)

    def _defer(self, trigger, mode, verdict):
        if self._deferred_row(trigger, mode) is not None:
            return None
        self._record_decided(trigger, mode, "deferred", verdict.generation, verdict.reason)
        return "{}deferred {}: {}".format(self._prefix(trigger), trigger.party, verdict.reason)

    def _deferred_row(self, trigger, mode):
        return self._ctx.conn.execute(
            "SELECT decided_at FROM dispatch_decisions WHERE project = ? AND key = ? AND mode = ?"
            " AND outcome = 'deferred'",
            (trigger.project, trigger.key, mode),
        ).fetchone()

    def retry_deferred(self, project_config, trigger, mode):
        deferred = self._deferred_row(trigger, mode)
        expired = (
            deferred is not None
            and not self._paused()
            and self._ctx.now - timeutil.from_iso(deferred["decided_at"]) > _DEFER_DEADLINE
        )
        if expired:
            return self._expire_deferred(trigger, mode)
        return self.decide(project_config, trigger, mode)

    def _expire_deferred(self, trigger, mode):
        self._record_decided(trigger, mode, "skipped", None, _DEFERRED_TOO_LONG)
        text = "dispatch gave up on {}: {}".format(trigger.party, _DEFERRED_TOO_LONG)
        self._post_notice(
            trigger.project, _Notice(text, "dispatch:{}:{}:expired".format(trigger.project, trigger.key))
        )
        return "{}skipped {}: {}".format(self._prefix(trigger), trigger.party, _DEFERRED_TOO_LONG)

    def _record_error(self, trigger, mode, error):
        existing = self._ctx.conn.execute(
            "SELECT 1 FROM dispatch_decisions WHERE project = ? AND key = ? AND mode = ?",
            (trigger.project, trigger.key, mode),
        ).fetchone()
        name = type(error).__name__
        if existing is None:
            self._record_decided(trigger, mode, "skipped", None, "error: {}".format(name))
        return "{}error {}: {}".format(self._prefix(trigger), trigger.party, name)

    def _record(self, party, project, kind, payload):
        with db.writing(self._ctx.conn):
            events.record(
                self._ctx.conn, self._ctx.now, self._ctx.origin, party, None, project, kind, "local", payload
            )

    def _record_decided(self, trigger, mode, outcome, generation, reason):
        self._record(
            trigger.party,
            trigger.project,
            "dispatch.decided",
            {
                "project": trigger.project,
                "rule": trigger.rule,
                "key": trigger.key,
                "mode": mode,
                "outcome": outcome,
                "party": trigger.party,
                "generation": generation,
                "subject": trigger.subject,
                "reason": reason,
            },
        )

    def _post_notice(self, project, notice):
        if notice_commands.announced(self._ctx.conn, notice.announces):
            return
        notice_commands.create_announcing(
            self._ctx, None, notice.text, "project:{}".format(project), _NOTICE_TTL, notice.announces
        )

    def _push(self, project_config, party, wait):
        notify_config = project_config.get("notify")
        if notify_config is None:
            return
        try:
            self._push_runner(notify_config["command"] + [party, wait])
        except OSError as error:
            sys.stderr.write("guild: notify command failed: {}\n".format(error))
