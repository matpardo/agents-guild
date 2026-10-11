from datetime import timedelta

from guild import config, db, dispatch_launch, dispatch_rules, events, locking, timeutil

_MAX_TRIGGER_AGE = timedelta(hours=1)
_LOCK_DIR_NAME = "dispatch"
_LOCK_FILE_NAME = "dispatch.lock"
_BUSY_LINE = "another dispatch pass is running"
_NOTHING_LINE = "nothing to dispatch"
_RECENT_LIMIT = 10
_IN_FLIGHT_STATES = ("launching", "launched")


def _cursors(conn):
    rows = conn.execute("SELECT project, last_seq FROM dispatch_cursors").fetchall()
    return {row["project"]: row["last_seq"] for row in rows}


def _set_cursor(conn, project, last_seq):
    conn.execute(
        "INSERT OR REPLACE INTO dispatch_cursors (project, last_seq) VALUES (?, ?)", (project, last_seq)
    )


def _drop_cursors_of_disabled(conn, known, enabled):
    with db.writing(conn):
        for project in known:
            if project not in enabled:
                conn.execute("DELETE FROM dispatch_cursors WHERE project = ?", (project,))


def _initialize_cursors(ctx, fresh, dry_run):
    seq = events.max_seq(ctx.conn)
    if not dry_run:
        with db.writing(ctx.conn):
            for project in fresh:
                _set_cursor(ctx.conn, project, seq)
    template = "{}: would initialize cursor at seq {}" if dry_run else "{}: cursor initialized at seq {}"
    return [template.format(project, seq) for project in fresh]


def _is_stale(ctx, event):
    return ctx.now - timeutil.from_iso(event["ts"]) > _MAX_TRIGGER_AGE


def _decision_line(launcher, project_config, trigger, mode, dry_run):
    if dry_run:
        return launcher.preview(project_config, trigger, mode)
    return launcher.decide(project_config, trigger, mode)


def _trigger_or_error(ctx, projects, trigger_for, event, lines):
    try:
        return trigger_for(ctx.conn, projects, event)
    except Exception as error:
        lines.append("{}: event {} skipped ({})".format(event["project"] or "-", event["seq"], type(error).__name__))
        return None


def _event_lines(ctx, launcher, projects, enabled, active, event, dry_run, ignored):
    lines = []
    for rule, trigger_for in dispatch_rules.RULES.items():
        trigger = _trigger_or_error(ctx, projects, trigger_for, event, lines)
        if trigger is None:
            continue
        project_config = enabled.get(trigger.project)
        cursor = active.get(trigger.project)
        if project_config is None or cursor is None or event["seq"] <= cursor:
            continue
        mode = project_config["dispatcher"]["rules"].get(rule)
        if mode is None:
            continue
        if _is_stale(ctx, event):
            ignored[trigger.project] = ignored.get(trigger.project, 0) + 1
            continue
        line = _decision_line(launcher, project_config, trigger, mode, dry_run)
        if line is not None:
            lines.append(line)
    return lines


def _state_triggers(ctx, trigger_for, project_config, lines):
    try:
        return trigger_for(ctx, project_config)
    except Exception as error:
        lines.append("{}: state rule skipped ({})".format(project_config["name"], type(error).__name__))
        return []


def _state_line(launcher, project_config, rule, trigger, mode, dry_run):
    if rule not in dispatch_rules.NOTIFY_ONLY_RULES:
        return _decision_line(launcher, project_config, trigger, mode, dry_run)
    if dry_run:
        return launcher.preview_announce(trigger, mode)
    return launcher.announce(project_config, trigger, mode)


def _state_lines(ctx, launcher, enabled, dry_run):
    lines = []
    for project_config in enabled.values():
        for rule, trigger_for in dispatch_rules.STATE_RULES.items():
            mode = project_config["dispatcher"]["rules"].get(rule)
            if mode is None:
                continue
            for trigger in _state_triggers(ctx, trigger_for, project_config, lines):
                line = _state_line(launcher, project_config, rule, trigger, mode, dry_run)
                if line is not None:
                    lines.append(line)
    return lines


def _deferred_lines(ctx, launcher, enabled, dry_run):
    rows = ctx.conn.execute(
        "SELECT * FROM dispatch_decisions WHERE outcome = 'deferred' ORDER BY decided_at ASC, rowid ASC"
    ).fetchall()
    lines = []
    for row in rows:
        project_config = enabled.get(row["project"])
        if project_config is None:
            continue
        mode = project_config["dispatcher"]["rules"].get(row["rule"])
        trigger = dispatch_rules.deferred_trigger(ctx.conn, row)
        if mode is None or trigger is None:
            continue
        line = _retry_line(launcher, project_config, trigger, mode, dry_run)
        if line is not None:
            lines.append(line)
    return lines


def _retry_line(launcher, project_config, trigger, mode, dry_run):
    if dry_run:
        return launcher.preview(project_config, trigger, mode)
    return launcher.retry_deferred(project_config, trigger, mode)


def _advance_cursors(ctx, active, new_events):
    last_seq = new_events[-1]["seq"]
    with db.writing(ctx.conn):
        for project in active:
            _set_cursor(ctx.conn, project, last_seq)


def _pass(ctx, launcher, dry_run):
    projects = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    enabled = {name: project for name, project in projects.items() if "dispatcher" in project}
    known = _cursors(ctx.conn)
    if not dry_run:
        _drop_cursors_of_disabled(ctx.conn, known, enabled)
    fresh = sorted(name for name in enabled if name not in known)
    lines = _initialize_cursors(ctx, fresh, dry_run) if fresh else []
    if not dry_run:
        lines.extend(launcher.reconcile(projects))
    lines.extend(_deferred_lines(ctx, launcher, enabled, dry_run))
    lines.extend(_state_lines(ctx, launcher, enabled, dry_run))
    active = {name: known[name] for name in enabled if name in known}
    if not active:
        return lines or [_NOTHING_LINE]
    new_events = events.events_after(ctx.conn, min(active.values()))
    ignored = {}
    for event in new_events:
        lines.extend(_event_lines(ctx, launcher, projects, enabled, active, event, dry_run, ignored))
    if new_events and not dry_run:
        _advance_cursors(ctx, active, new_events)
    for project in sorted(ignored):
        lines.append("{}: {} events older than 1h ignored".format(project, ignored[project]))
    return lines or [_NOTHING_LINE]


def run(ctx, dry_run, tmux, push_runner):
    launcher = dispatch_launch.Launcher(ctx, tmux, push_runner)
    if dry_run:
        return _pass(ctx, launcher, True)
    with locking.try_lock(ctx.state_dir / _LOCK_DIR_NAME, _LOCK_FILE_NAME) as acquired:
        if not acquired:
            return [_BUSY_LINE]
        return _pass(ctx, launcher, False)


def _in_flight_line(ctx, row):
    return "  in flight: {} g{} window {} launched {} ago ({})".format(
        row["party"],
        row["generation"],
        row["window_id"] or "-",
        timeutil.age_label(ctx.now, row["decided_at"]),
        row["subject"],
    )


def _outcome_label(row):
    if row["outcome"] in ("skipped", "deferred"):
        return "{} {}: {}".format(row["outcome"], row["party"], row["reason"])
    verb = "launched" if row["outcome"] == "launching" else row["outcome"]
    label = "{} {} g{}".format(verb, row["party"], row["generation"])
    if row["state"] is None:
        return label
    return "{} [{}]".format(label, row["state"])


def _recent_line(row):
    stamp = timeutil.from_iso(row["decided_at"]).strftime("%Y-%m-%dT%H:%M")
    return "    {} {} {} -> {}".format(stamp, row["rule"], row["subject"], _outcome_label(row))


def _project_status(ctx, project_config, cursors):
    name = project_config["name"]
    block = project_config["dispatcher"]
    cursor = cursors.get(name)
    lines = [
        "{}: cursor {} | launches last hour {}/{} | mode {}".format(
            name,
            "not initialized" if cursor is None else cursor,
            dispatch_launch.launches_last_hour(ctx.conn, ctx.now, name),
            block["max_launches_per_hour"],
            block["permission_mode"],
        )
    ]
    lines.extend("  {}: {}".format(rule, block["rules"][rule]) for rule in sorted(block["rules"]))
    rows = ctx.conn.execute(
        "SELECT * FROM dispatch_decisions WHERE project = ? ORDER BY decided_at DESC, rowid DESC", (name,)
    ).fetchall()
    lines.extend(_in_flight_line(ctx, row) for row in rows if row["state"] in _IN_FLIGHT_STATES)
    if rows:
        lines.append("  recent:")
        lines.extend(_recent_line(row) for row in rows[:_RECENT_LIMIT])
    return lines


def status(ctx):
    cursors = _cursors(ctx.conn)
    lines = []
    for project_config in config.load_all_projects(ctx.projects_dir):
        if "dispatcher" not in project_config:
            lines.append("{}: dispatcher not configured".format(project_config["name"]))
            continue
        lines.extend(_project_status(ctx, project_config, cursors))
    return lines
