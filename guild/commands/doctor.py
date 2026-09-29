import json
from pathlib import Path

from guild import config
from guild.errors import GuildError

_EXPECTED_HOOKS = (
    ("SessionStart", "guild hook session-start"),
    ("UserPromptSubmit", "guild hook prompt-submit"),
    ("PostToolUse", "guild hook post-tool-use"),
    ("PreToolUse", "guild hook pre-push"),
    ("PreToolUse", "guild hook pre-edit"),
)


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
    return lines


def run(ctx):
    checks = _hook_lines(_claude_dir() / "settings.json")
    checks.append(_rules_line())
    checks.extend(_project_lines(ctx.projects_dir))
    healthy = all(passed for passed, _ in checks)
    lines = [line for _, line in checks]
    if not healthy:
        lines.append("see README (Hooks, Install) for the missing pieces")
    return "\n".join(lines), 0 if healthy else 1
