import re
from pathlib import Path

from guild import claude_settings, config, localbase
from guild.adapters import github
from guild.errors import GuildError

_TRACE_RE = re.compile(r"guild|ask #[0-9]|notice #[0-9]", re.IGNORECASE)
_PR_SCAN_FIELDS = ("number", "title", "body", "comments", "commits")


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
    return lines


def _allow_rule_lines(settings):
    configured = settings.get("permissions", {}).get("allow", [])
    blanket = any(rule in configured for rule in claude_settings.BLANKET_ALLOW_RULES)
    lines = []
    for rule in claude_settings.EXPECTED_ALLOW_RULES:
        if blanket or rule in configured:
            lines.append((True, "ok      allow rule {}".format(rule)))
            continue
        lines.append(
            (True, "warn    allow rule missing {} (a permission prompt can stall the session)".format(rule))
        )
    return lines


def _rules_line():
    present = (_claude_dir() / "GUILD.md").exists()
    if present:
        return True, "ok      ~/.claude/GUILD.md"
    return False, "missing ~/.claude/GUILD.md (run install.sh)"


def _project_lines(projects_dir):
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
    if any(
        _has_trace(commit["messageHeadline"]) or _has_trace(commit["messageBody"])
        for commit in pr["commits"]
    ):
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


def run(ctx, scan_prs):
    settings = claude_settings.load_settings(_claude_dir() / "settings.json")
    checks = _hook_lines(settings)
    checks.extend(_ask_rule_lines(settings))
    checks.extend(_allow_rule_lines(settings))
    checks.append(_rules_line())
    checks.extend(_project_lines(ctx.projects_dir))
    if scan_prs:
        checks.extend(_scan_lines(ctx))
    healthy = all(passed for passed, _ in checks)
    lines = [line for _, line in checks]
    if not healthy:
        lines.append("see README (Hooks, Install) for the missing pieces")
    return "\n".join(lines), 0 if healthy else 1
