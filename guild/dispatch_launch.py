import os
import sys
from datetime import timedelta
from pathlib import Path

from guild import config, db, events, resume, session_info, timeutil, tmux_windows
from guild.adapters import github
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands

_DUPLICATE = "duplicate"
_BUSY = "busy"
_SKIP = "skip"
_PLAN = "plan"
_LAUNCH = "launch"
_DRY_RUN_MODE = "dry-run"
_REAL_MODE = "on"
_HANDED_OFF_STATE = "awaiting-leader"
_CLOSED_STATE = "closed"
_MODES_BY_PERMISSIVENESS = ("plan", "manual", "acceptEdits", "auto")
_IN_FLIGHT_STATES = ("launching", "launched")
_RATE_WINDOW = timedelta(hours=1)
_NOTICE_TTL = "12h"
_WINDOW_FAILURE = "tmux could not create the window"
_FAILURE_WAIT = "dispatch-failed"
_MERGE_HEAD_WAIT = "merge-head"
_PROMOTE_WAIT = "pr-promote"
_HOUR_FORMAT = "%Y-%m-%dT%H"
_BIND_DEADLINE = timedelta(minutes=10)
_DEFER_DEADLINE = timedelta(hours=24)
_DEFERRED_TOO_LONG = "deferred too long"


class _Notice:
    def __init__(self, text, announces):
        self.text = text
        self.announces = announces


class Verdict:
    def __init__(self, kind, reason, notice, generation, permission_mode, cwd):
        self.kind = kind
        self.reason = reason
        self.notice = notice
        self.generation = generation
        self.permission_mode = permission_mode
        self.cwd = cwd


def effective_mode(configured_mode, party_mode):
    if party_mode not in _MODES_BY_PERMISSIVENESS:
        return configured_mode
    return min(configured_mode, party_mode, key=_MODES_BY_PERMISSIVENESS.index)


def launches_last_hour(conn, now, project):
    rows = conn.execute(
        "SELECT decided_at FROM dispatch_decisions WHERE project = ? AND mode = 'on' AND outcome = 'launching'",
        (project,),
    ).fetchall()
    return len([row for row in rows if now - timeutil.from_iso(row["decided_at"]) <= _RATE_WINDOW])


def _verdict_without_launch(kind, reason, notice, generation):
    return Verdict(kind, reason, notice, generation, None, None)


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
            return self._record_error(project_config, trigger, mode, error)

    def announce(self, project_config, trigger, mode):
        try:
            return self._announce(project_config, trigger, mode)
        except Exception as error:
            return self._record_error(project_config, trigger, mode, error)

    def preview_announce(self, trigger, mode):
        if self._already_decided(trigger, mode):
            return None
        return "{}would notify {}".format(self._prefix(trigger), trigger.party)

    def promote(self, project_config, trigger, mode):
        try:
            return self._promote(project_config, trigger, mode)
        except Exception as error:
            return self._record_error(project_config, trigger, mode, error)

    def preview_promote(self, trigger, mode):
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
            self._record_decided(trigger, mode, "planned", None, None, None)
            return "{}planned: {} {}".format(prefix, verb, trigger.party)
        if not trigger.needs_human_review:
            try:
                github.pr_ready(self._ctx.cwd, trigger.repo, trigger.number)
            except github.GhCommandError as error:
                return self._promote_failure(project_config, trigger, mode, str(error))
        outcome = "notified" if trigger.needs_human_review else "promoted"
        self._record_decided(trigger, mode, outcome, None, None, None)
        announces = "dispatch:{}:{}:{}".format(trigger.project, trigger.key, outcome)
        self._post_notice(trigger.project, _Notice(trigger.prompt, announces))
        self._push(project_config, trigger.party, _PROMOTE_WAIT)
        return "{}{} {}".format(prefix, outcome, trigger.party)

    def _promote_failure(self, project_config, trigger, mode, reason):
        self._record_decided(trigger, mode, "failed", None, None, reason)
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
            self._record_decided(trigger, mode, "planned", None, None, None)
            return "{}planned: notify {}".format(prefix, trigger.party)
        self._record_decided(trigger, mode, "notified", None, None, None)
        announces = "dispatch:{}:{}:notified".format(trigger.project, trigger.key)
        self._post_notice(trigger.project, _Notice(trigger.prompt, announces))
        self._push(project_config, trigger.party, _MERGE_HEAD_WAIT)
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
        verb = "would plan launch" if verdict.kind == _PLAN else "would launch"
        return "{}{} {} g{} (mode {})".format(
            prefix, verb, trigger.party, verdict.generation, verdict.permission_mode
        )

    def evaluate(self, project_config, trigger, mode):
        if self._already_decided(trigger, mode):
            return _verdict_without_launch(_DUPLICATE, None, None, None)
        party = self._ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (trigger.party,)).fetchone()
        verdict = self._standing(trigger, party)
        if verdict is not None:
            return verdict
        generation = party["generation"] + 1
        leader = self._ctx.conn.execute(
            "SELECT cwd, permission_mode FROM leaders WHERE party = ? AND generation = ?",
            (trigger.party, party["generation"]),
        ).fetchone()
        verdict = (
            self._breaker(trigger, party, generation)
            or self._location(trigger, leader, generation)
            or self._tmux_session(trigger, generation)
            or self._rate_limit(project_config, trigger, generation)
        )
        if verdict is not None:
            return verdict
        kind = _PLAN if mode == _DRY_RUN_MODE else _LAUNCH
        party_mode = None if leader is None else leader["permission_mode"]
        permission_mode = effective_mode(project_config["dispatcher"]["permission_mode"], party_mode)
        return Verdict(kind, None, None, generation, permission_mode, leader["cwd"])

    def reconcile(self, projects):
        rows = self._ctx.conn.execute(
            "SELECT * FROM dispatch_decisions WHERE mode = 'on' AND state IN ('launching', 'launched')"
            " ORDER BY decided_at ASC, rowid ASC"
        ).fetchall()
        lines = []
        for row in rows:
            project_config = projects.get(row["project"])
            if project_config is None:
                continue
            line = self._reconcile_row(project_config, row)
            if line is not None:
                lines.append(line)
        return lines

    def _reconcile_row(self, project_config, row):
        label = "{} g{}".format(row["party"], row["generation"])
        party = self._ctx.conn.execute(
            "SELECT generation FROM parties WHERE name = ?", (row["party"],)
        ).fetchone()
        if party is not None and party["generation"] >= row["generation"]:
            self._record(
                row["party"],
                row["project"],
                "dispatch.bound",
                {
                    "project": row["project"],
                    "key": row["key"],
                    "party": row["party"],
                    "generation": row["generation"],
                },
            )
            return "{} bound".format(label)
        reason = self._unbound_reason(row)
        if reason is None:
            return None
        self._fail_launch(project_config, row["key"], row["party"], row["generation"], reason, row["window_id"])
        return "{} launch failed: {}".format(label, reason)

    def _unbound_reason(self, row):
        if row["state"] == "launching":
            return "launch interrupted"
        if not self._tmux.installed() or not tmux_windows.window_in_session(self._tmux, row["window_id"]):
            return "window exited before binding"
        if self._ctx.now - timeutil.from_iso(row["decided_at"]) > _BIND_DEADLINE:
            return "did not bind within 10m; window {} left running".format(row["window_id"])
        return None

    def _report_failure(self, project_config, party, generation, key, reason):
        project = project_config["name"]
        text = "dispatch launch failed for {} g{}: {}".format(party, generation, reason)
        self._post_notice(project, _Notice(text, "dispatch:{}:{}:failed".format(project, key)))
        self._push(project_config, party, _FAILURE_WAIT)

    def _fail_launch(self, project_config, key, party, generation, reason, window_id):
        project = project_config["name"]
        self._record(
            party,
            project,
            "dispatch.launch_failed",
            {
                "project": project,
                "key": key,
                "party": party,
                "generation": generation,
                "reason": reason,
                "window_id": window_id,
            },
        )
        self._report_failure(project_config, party, generation, key, reason)

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
            return _verdict_without_launch(_SKIP, "party closed", None, generation)
        generation = party["generation"] + 1
        if party["keeper"]:
            return _verdict_without_launch(_SKIP, "keeper", None, generation)
        busy_reason = self._busy_reason(trigger, party)
        if busy_reason is not None:
            return _verdict_without_launch(_BUSY, busy_reason, None, generation)
        if party["state"] != _HANDED_OFF_STATE:
            text = "dispatch skipped for {}: it did not hand off; run guild revive --party {}".format(
                trigger.party, trigger.party
            )
            notice = _Notice(text, "dispatch:{}:{}:skipped".format(trigger.project, trigger.key))
            return _verdict_without_launch(_SKIP, "party not handed off", notice, generation)
        return None

    def _busy_reason(self, trigger, party):
        conn, ctx = self._ctx.conn, self._ctx
        if party["leader_session_id"] in session_info.live_session_ids(ctx.sessions_dir):
            return "live session"
        if self._tmux.installed() and trigger.party in tmux_windows.window_names(self._tmux):
            return "open window"
        in_flight = conn.execute(
            "SELECT 1 FROM dispatch_decisions WHERE party = ? AND state IN ('launching', 'launched')",
            (trigger.party,),
        ).fetchone()
        if in_flight is not None:
            return "launch in flight"
        paused = raid_commands.paused_member_raids(conn, ctx.now, trigger.party)
        if paused:
            return "raid {} paused".format(paused[0]["raid"])
        return None

    def _breaker(self, trigger, party, generation):
        blocked = self._ctx.conn.execute(
            "SELECT 1 FROM dispatch_decisions WHERE party = ? AND state = 'failed' AND generation > ?",
            (trigger.party, party["generation"]),
        ).fetchone()
        if blocked is None:
            return None
        return _verdict_without_launch(_SKIP, "previous launch did not bind", None, generation)

    def _skip_with_notice(self, trigger, generation, reason, announces):
        text = "dispatch skipped for {}: {}".format(trigger.party, reason)
        return _verdict_without_launch(_SKIP, reason, _Notice(text, announces), generation)

    def _location(self, trigger, leader, generation):
        announces = "dispatch:{}:{}:skipped".format(trigger.project, trigger.key)
        cwd = None if leader is None else leader["cwd"]
        if cwd is None:
            return self._skip_with_notice(trigger, generation, "cwd unknown", announces)
        if "#" in cwd:
            return self._skip_with_notice(trigger, generation, "cwd unsafe", announces)
        if not os.path.isdir(cwd):
            return self._skip_with_notice(trigger, generation, "cwd missing", announces)
        projects = config.load_all_projects(self._ctx.projects_dir)
        if config.resolve_project(Path(cwd), projects) != trigger.project:
            return self._skip_with_notice(trigger, generation, "cwd outside project", announces)
        return None

    def _tmux_session(self, trigger, generation):
        if self._tmux.installed() and tmux_windows.session_exists(self._tmux):
            return None
        hour = self._ctx.now.strftime(_HOUR_FORMAT)
        text = (
            "dispatch skipped for {}: tmux session {} is not running;"
            " start it with tmux new -s {} or run guild revive"
        ).format(trigger.party, tmux_windows.SESSION, tmux_windows.SESSION)
        notice = _Notice(text, "dispatch:{}:no-tmux:{}".format(trigger.project, hour))
        return _verdict_without_launch(
            _SKIP, "tmux session {} not running".format(tmux_windows.SESSION), notice, generation
        )

    def _rate_limit(self, project_config, trigger, generation):
        limit = project_config["dispatcher"]["max_launches_per_hour"]
        used = launches_last_hour(self._ctx.conn, self._ctx.now, trigger.project)
        if used < limit:
            return None
        reason = "rate limit ({}/{})".format(used, limit)
        hour = self._ctx.now.strftime(_HOUR_FORMAT)
        text = "dispatch skipped for {}: {}".format(trigger.party, reason)
        notice = _Notice(text, "dispatch:{}:rate:{}".format(trigger.project, hour))
        return _verdict_without_launch(_SKIP, reason, notice, generation)

    def _execute(self, project_config, trigger, mode, verdict):
        if verdict.kind == _DUPLICATE:
            return None
        prefix = self._prefix(trigger)
        if verdict.kind == _BUSY:
            return self._defer(trigger, mode, verdict)
        if verdict.kind == _SKIP:
            self._record_decided(trigger, mode, "skipped", verdict.generation, None, verdict.reason)
            if verdict.notice is not None:
                self._post_notice(trigger.project, verdict.notice)
            return "{}skipped {}: {}".format(prefix, trigger.party, verdict.reason)
        if verdict.kind == _PLAN:
            self._record_decided(trigger, mode, "planned", verdict.generation, verdict.permission_mode, None)
            return "{}planned: launch {} g{} ({}, mode {})".format(
                prefix, trigger.party, verdict.generation, mode, verdict.permission_mode
            )
        return self._launch(project_config, trigger, mode, verdict)

    def _defer(self, trigger, mode, verdict):
        if self._deferred_row(trigger, mode) is not None:
            return None
        self._record_decided(trigger, mode, "deferred", verdict.generation, None, verdict.reason)
        return "{}deferred {}: {}".format(self._prefix(trigger), trigger.party, verdict.reason)

    def _deferred_row(self, trigger, mode):
        return self._ctx.conn.execute(
            "SELECT decided_at FROM dispatch_decisions WHERE project = ? AND key = ? AND mode = ?"
            " AND outcome = 'deferred'",
            (trigger.project, trigger.key, mode),
        ).fetchone()

    def retry_deferred(self, project_config, trigger, mode):
        deferred = self._deferred_row(trigger, mode)
        if deferred is not None and self._ctx.now - timeutil.from_iso(deferred["decided_at"]) > _DEFER_DEADLINE:
            return self._expire_deferred(trigger, mode)
        return self.decide(project_config, trigger, mode)

    def _expire_deferred(self, trigger, mode):
        self._record_decided(trigger, mode, "skipped", None, None, _DEFERRED_TOO_LONG)
        text = "dispatch gave up on {}: {}".format(trigger.party, _DEFERRED_TOO_LONG)
        self._post_notice(
            trigger.project, _Notice(text, "dispatch:{}:{}:expired".format(trigger.project, trigger.key))
        )
        return "{}skipped {}: {}".format(self._prefix(trigger), trigger.party, _DEFERRED_TOO_LONG)

    def _launch(self, project_config, trigger, mode, verdict):
        prefix = self._prefix(trigger)
        self._record_decided(trigger, mode, "launching", verdict.generation, verdict.permission_mode, None)
        window_id = None
        try:
            command = resume.fresh_command(
                trigger.party, verdict.generation, None, verdict.permission_mode, False, trigger.prompt
            )
            window_id = tmux_windows.create_window(self._tmux, trigger.party, verdict.cwd, command, True)
            if window_id is None:
                return self._launch_failure(project_config, trigger, verdict, _WINDOW_FAILURE, None)
            tmux_windows.pin_window_name(self._tmux, window_id)
            self._record_window(trigger, verdict, window_id)
            self._record_launched(trigger, verdict, window_id)
        except Exception as error:
            return self._launch_failure(project_config, trigger, verdict, type(error).__name__, window_id)
        return "{}launched {} g{} (window {}, mode {})".format(
            prefix, trigger.party, verdict.generation, window_id, verdict.permission_mode
        )

    def _launch_failure(self, project_config, trigger, verdict, reason, window_id):
        self._fail_launch(project_config, trigger.key, trigger.party, verdict.generation, reason, window_id)
        return "{}launch failed {} g{}: {}".format(
            self._prefix(trigger), trigger.party, verdict.generation, reason
        )

    def _record_error(self, project_config, trigger, mode, error):
        name = type(error).__name__
        existing = self._ctx.conn.execute(
            "SELECT generation, state, window_id FROM dispatch_decisions WHERE project = ? AND key = ? AND mode = ?",
            (trigger.project, trigger.key, mode),
        ).fetchone()
        if existing is None:
            self._record_decided(trigger, mode, "skipped", None, None, "error: {}".format(name))
        elif existing["state"] == "launching":
            return self._launch_failure_line(project_config, trigger, existing, name)
        return "{}error {}: {}".format(self._prefix(trigger), trigger.party, name)

    def _launch_failure_line(self, project_config, trigger, row, reason):
        self._fail_launch(project_config, trigger.key, trigger.party, row["generation"], reason, row["window_id"])
        return "{}launch failed {} g{}: {}".format(self._prefix(trigger), trigger.party, row["generation"], reason)

    def _record(self, party, project, kind, payload):
        with db.writing(self._ctx.conn):
            events.record(
                self._ctx.conn, self._ctx.now, self._ctx.origin, party, None, project, kind, "local", payload
            )

    def _record_decided(self, trigger, mode, outcome, generation, permission_mode, reason):
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
                "permission_mode": permission_mode,
                "subject": trigger.subject,
                "reason": reason,
            },
        )

    def _record_window(self, trigger, verdict, window_id):
        self._record(
            trigger.party,
            trigger.project,
            "leader.window_launched",
            {"party": trigger.party, "generation": verdict.generation, "window_id": window_id},
        )

    def _record_launched(self, trigger, verdict, window_id):
        self._record(
            trigger.party,
            trigger.project,
            "dispatch.launched",
            {
                "project": trigger.project,
                "key": trigger.key,
                "party": trigger.party,
                "generation": verdict.generation,
                "window_id": window_id,
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
