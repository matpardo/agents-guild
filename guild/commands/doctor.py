import json
import re
from pathlib import Path

from guild import config, localbase
from guild.adapters import github
from guild.errors import GuildError

_EXPECTED_HOOKS = (
    ("SessionStart", "guild hook session-start"),
    ("UserPromptSubmit", "guild hook prompt-submit"),
    ("PostToolUse", "guild hook post-tool-use"),
    ("PreToolUse", "guild hook pre-push"),
    ("PreToolUse", "guild hook pre-edit"),
)


_TRACE_RE = re.compile(r"guild|ask #[0-9]|notice #[0-9]", re.IGNORECASE)
_PR_SCAN_FIELDS = ("number", "title", "body", "comments", "commits")


def _claude_dir():
    return Path.home() / ".claude"


def _configured_commands(settings_path):
    if not settings_path.is_file():
        return {}
    try:
        hooks = json.loads(settings_path.read_text()).get("hooks", {})
    except json.JSONDecodeError as error:
        raise GuildError("invalid JSON in {}: {}".format(settings_path, error), 1)
    commands = {}
    for event, entries in hooks.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                commands.setdefault(event, []).append(hook.get("command", ""))
    return commands


def _hook_lines(settings_path):
    commands = _configured_commands(settings_path)
    lines = []
    for event, expected in _EXPECTED_HOOKS:
        wired = any(command.endswith(expected) for command in commands.get(event, []))
        status = "ok     " if wired else "missing"
        lines.append((wired, "{} hook {}: {}".format(status, event, expected)))
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
    checks = _hook_lines(_claude_dir() / "settings.json")
    checks.append(_rules_line())
    checks.extend(_project_lines(ctx.projects_dir))
    if scan_prs:
        checks.extend(_scan_lines(ctx))
    healthy = all(passed for passed, _ in checks)
    lines = [line for _, line in checks]
    if not healthy:
        lines.append("see README (Hooks, Install) for the missing pieces")
    return "\n".join(lines), 0 if healthy else 1
