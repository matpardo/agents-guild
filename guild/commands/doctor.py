import re
import shutil
from pathlib import Path

from guild import claude_settings, config, ctx_pressure, identity, localbase, paths, statusline_state, tmux_windows
from guild.adapters import github
from guild.commands import realm as realm_commands
from guild.errors import GuildError
from guild.realm import checks as realm_checks

_TRACE_RE = re.compile(r"guild|ask #[0-9]|notice #[0-9]", re.IGNORECASE)
_PR_SCAN_FIELDS = ("number", "title", "body", "comments", "commits")
_DATED_COLUMNS = (
    ("quests", "created_at"),
    ("quest_tasks", "created_at"),
    ("prs", "tracked_at"),
    ("claims", "created_at"),
    ("parties", "updated_at"),
)


def _claude_dir():
    return Path.home() / ".claude"


def _hook_lines(settings):
    commands = claude_settings.configured_commands(settings)
    lines = []
    for event, _, expected in claude_settings.EXPECTED_HOOKS:
        wired = claude_settings.hook_is_wired(commands, event, expected)
        status = "ok     " if wired else "missing"
        lines.append((wired, "{} hook {}: {}".format(status, event, expected)))
    return lines


def _ask_rule_lines(settings):
    configured = settings.get("permissions", {}).get("ask", [])
    lines = []
    for rule in claude_settings.EXPECTED_ASK_RULES:
        present = rule in configured
        status = "ok     " if present else "missing"
        lines.append((present, "{} ask rule {}".format(status, rule)))
    for rule in claude_settings.RETIRED_ASK_RULES:
        if rule in configured:
            lines.append((True, "warn    retired ask rule {} (run guild wire-settings)".format(rule)))
    return lines


def _allow_rule_lines(settings):
    configured = settings.get("permissions", {}).get("allow", [])
    blanket = any(rule in configured for rule in claude_settings.BLANKET_ALLOW_RULES)
    lines = []
    for rule in claude_settings.EXPECTED_ALLOW_RULES:
        if blanket or rule in configured:
            lines.append((True, "ok      allow rule {}".format(rule)))
            continue
        lines.append((True, "warn    allow rule missing {} (a permission prompt can stall the session)".format(rule)))
    return lines


def _rules_line():
    present = (_claude_dir() / "GUILD.md").exists()
    if present:
        return True, "ok      ~/.claude/GUILD.md"
    return False, "missing ~/.claude/GUILD.md (run install.sh)"


def _clipboard_lines():
    if shutil.which("tmux") is None or tmux_windows.clipboard_command() is not None:
        return []
    return [
        (
            True,
            "warn    tmux copy reaches the clipboard only through the terminal (OSC 52): "
            "install xclip (X11) or wl-clipboard (Wayland)",
        )
    ]


def _global_config_lines(global_config_path):
    try:
        return config.load_global(global_config_path), []
    except GuildError as error:
        return None, [(False, "invalid {}".format(error.message))]


def _guild_name_lines(global_config):
    if global_config is None:
        return []
    name = global_config.get("name")
    if name is not None:
        return [(True, "ok      guild name {}".format(name))]
    return [(True, "warn    guild has no name: {}".format(realm_commands.missing_name_hint()))]


def _handoff_line(state_dir, global_config):
    resolved = ctx_pressure.threshold(state_dir, global_config, None)
    if resolved["source"] == "configured":
        return []
    lines = [(True, "ok      handoff at {}% ({})".format(resolved["value"], resolved["source"]))]
    baseline = statusline_state.latest_baseline(state_dir)
    floored = ctx_pressure.floor_above_baseline(resolved, baseline)
    if floored is resolved:
        return lines
    message = "warn    handoff at {}% is under {} points above a fresh session at {}%: sessions hand off at {}% instead"
    lines.append((True, message.format(resolved["value"], ctx_pressure.BASELINE_HEADROOM, baseline, floored["value"])))
    return lines


def _compaction_lines(state_dir, global_config, data):
    if global_config is None or global_config.get("handoff_margin") is not None:
        return []
    compaction = statusline_state.latest_compact_pct(state_dir)
    if compaction is None:
        return []
    threshold = ctx_pressure.threshold(state_dir, global_config, data)["value"]
    if threshold < compaction:
        return []
    message = (
        "warn    project {} handoff_threshold {}% is above the last compaction at {}%: lower it or set handoff_margin"
    )
    return [(True, message.format(data["name"], threshold, compaction))]


def _project_lines(projects_dir, state_dir, global_config):
    if not projects_dir.is_dir():
        return []
    lines = []
    for config_file in sorted(projects_dir.glob("*.json")):
        try:
            data = config.load_project_file(config_file)
        except GuildError as error:
            lines.append((False, "invalid project {}: {}".format(config_file.name, error.message)))
            continue
        lines.append((True, "ok      project {}".format(data["name"])))
        if "dispatcher" in data:
            lines.append(
                (
                    True,
                    "warn    project {} still has a 'dispatcher' key: the dispatcher was retired, remove it".format(
                        data["name"]
                    ),
                )
            )
        lines.extend(_compaction_lines(state_dir, global_config, data))
        for warning in localbase.behind_warning_lines(data):
            lines.append((True, "warn    {}".format(warning)))
    return lines


def _has_trace(text):
    return text is not None and _TRACE_RE.search(text) is not None


def _pr_trace_places(pr):
    places = []
    if _has_trace(pr["title"]):
        places.append("title")
    if _has_trace(pr["body"]):
        places.append("body")
    if any(_has_trace(comment["body"]) for comment in pr["comments"]):
        places.append("comment")
    if any(_has_trace(commit["messageHeadline"]) or _has_trace(commit["messageBody"]) for commit in pr["commits"]):
        places.append("commit")
    return places


def _scan_lines(ctx):
    lines = []
    for project in config.load_all_projects(ctx.projects_dir):
        for repo in project["github"]["repos"]:
            try:
                open_prs = github.pr_list_open(ctx.cwd, repo, _PR_SCAN_FIELDS)
            except github.GhCommandError as error:
                return [(True, "warn    PR scan skipped: {}".format(error))]
            for pr in open_prs:
                for place in _pr_trace_places(pr):
                    lines.append(
                        (True, "warn    {}#{} {} mentions guild-internal terms".format(repo, pr["number"], place))
                    )
    return lines


def _undated_lines(conn):
    total = sum(
        conn.execute("SELECT COUNT(*) FROM {} WHERE {} IS NULL".format(table, column)).fetchone()[0]
        for table, column in _DATED_COLUMNS
    )
    if total == 0:
        return []
    message = "warn    {} rows predate stored dates: run guild compact, then guild rebuild, with no session working"
    return [(True, message.format(total))]


def run(ctx, scan_prs):
    settings = claude_settings.load_settings(_claude_dir() / "settings.json")
    checks = _hook_lines(settings)
    checks.extend(_ask_rule_lines(settings))
    checks.extend(_allow_rule_lines(settings))
    checks.append(_rules_line())
    checks.extend(_clipboard_lines())
    global_config, global_lines = _global_config_lines(paths.global_config_path())
    checks.extend(global_lines)
    if global_config is not None:
        checks.extend(_handoff_line(ctx.state_dir, global_config))
    checks.extend(_guild_name_lines(global_config))
    checks.extend(realm_checks.config_lines())
    checks.extend(_undated_lines(ctx.conn))
    checks.extend(_project_lines(ctx.projects_dir, ctx.state_dir, global_config))
    checks.extend((True, "warn    {}".format(finding)) for finding in identity.double_bindings(ctx.conn, None))
    if scan_prs:
        checks.extend(_scan_lines(ctx))
    healthy = all(passed for passed, _ in checks)
    lines = [line for _, line in checks]
    if not healthy:
        lines.append("see docs/hooks.md and the README Install section for the missing pieces")
    return "\n".join(lines), 0 if healthy else 1
