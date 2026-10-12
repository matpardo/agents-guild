import json

from guild.errors import GuildError

_EDIT_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"

EXPECTED_HOOKS = (
    ("SessionStart", None, "guild hook session-start"),
    ("UserPromptSubmit", None, "guild hook prompt-submit"),
    ("PostToolUse", None, "guild hook post-tool-use"),
    ("PreToolUse", "Bash", "guild hook pre-push"),
    ("PreToolUse", _EDIT_MATCHER, "guild hook pre-edit"),
    ("PreToolUse", "Bash", "guild hook pre-pr-owner"),
    ("PreToolUse", "Bash", "guild hook pre-answer"),
    ("Notification", None, "guild hook notification"),
    ("Stop", None, "guild hook stop"),
)

EXPECTED_ASK_RULES = ("Bash(guild party start:*)", "Bash(guild quest add:*)")

EXPECTED_ALLOW_RULES = (
    "Bash(guild task:*)",
    "Bash(guild pr:*)",
    "Bash(guild finding:*)",
    "Bash(guild notice:*)",
    "Bash(guild ask:*)",
    "Bash(guild next:*)",
    "Bash(guild claim:*)",
    "Bash(guild release:*)",
    "Bash(guild raid:*)",
    "Bash(guild handoff:*)",
    "Bash(guild sync:*)",
    "Bash(guild memory:*)",
)

BLANKET_ALLOW_RULES = ("Bash(guild:*)", "Bash(guild *)")


def load_settings(settings_path):
    if not settings_path.is_file():
        return {}
    try:
        return json.loads(settings_path.read_text())
    except json.JSONDecodeError as error:
        raise GuildError("invalid JSON in {}: {}".format(settings_path, error), 1)


def configured_commands(settings):
    commands = {}
    for event, entries in settings.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                commands.setdefault(event, []).append(hook.get("command", ""))
    return commands


def hook_is_wired(commands, event, expected):
    return any(command.endswith(expected) for command in commands.get(event, []))
