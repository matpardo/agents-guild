import json
from pathlib import Path

from guild import claude_settings


def _is_guild_hook(event, hook):
    command = hook.get("command", "")
    return any(
        command.endswith(expected)
        for expected_event, _, expected in claude_settings.EXPECTED_HOOKS
        if expected_event == event
    )


def _remove_hooks(settings):
    removed = []
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        kept_entries = []
        for entry in hooks[event]:
            kept = []
            for hook in entry.get("hooks", []):
                if _is_guild_hook(event, hook):
                    removed.append("removed hook {}: {}".format(event, hook.get("command", "")))
                    continue
                kept.append(hook)
            if kept:
                kept_entries.append({**entry, "hooks": kept})
                continue
            if not entry.get("hooks"):
                kept_entries.append(entry)
        if kept_entries:
            hooks[event] = kept_entries
            continue
        del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    return removed


def _remove_rules(settings, kind, guild_rules):
    permissions = settings.get("permissions", {})
    configured = permissions.get(kind, [])
    found = [rule for rule in configured if rule in guild_rules]
    if not found:
        return []
    kept = [rule for rule in configured if rule not in guild_rules]
    if kept:
        permissions[kind] = kept
    else:
        del permissions[kind]
    if not permissions:
        del settings["permissions"]
    return ["removed {} rule {}".format(kind, rule) for rule in found]


def run():
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = claude_settings.load_settings(settings_path)
    removed = _remove_hooks(settings)
    ask_rules = claude_settings.EXPECTED_ASK_RULES + claude_settings.RETIRED_ASK_RULES
    allow_rules = claude_settings.EXPECTED_ALLOW_RULES + claude_settings.BLANKET_ALLOW_RULES
    removed.extend(_remove_rules(settings, "ask", ask_rules))
    removed.extend(_remove_rules(settings, "allow", allow_rules))
    if not removed:
        return "settings: nothing wired ({})".format(settings_path)
    settings_path.with_name(settings_path.name + ".bak").write_bytes(settings_path.read_bytes())
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return "\n".join(removed)
