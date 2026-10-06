import json
from pathlib import Path

from guild import claude_settings


def _hook_entry(matcher, command):
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher is None:
        return entry
    return {"matcher": matcher, **entry}


def _add_hooks(settings):
    commands = claude_settings.configured_commands(settings)
    added = []
    for event, matcher, command in claude_settings.EXPECTED_HOOKS:
        if claude_settings.hook_is_wired(commands, event, command):
            continue
        settings.setdefault("hooks", {}).setdefault(event, []).append(_hook_entry(matcher, command))
        added.append("added hook {}: {}".format(event, command))
    return added


def _add_rules(settings, kind, expected_rules):
    configured = settings.get("permissions", {}).get(kind, [])
    added = []
    for rule in expected_rules:
        if rule in configured:
            continue
        settings.setdefault("permissions", {}).setdefault(kind, []).append(rule)
        added.append("added {} rule {}".format(kind, rule))
    return added


def _add_allow_rules(settings):
    configured = settings.get("permissions", {}).get("allow", [])
    if any(rule in configured for rule in claude_settings.BLANKET_ALLOW_RULES):
        return []
    return _add_rules(settings, "allow", claude_settings.EXPECTED_ALLOW_RULES)


def run():
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = claude_settings.load_settings(settings_path)
    original = settings_path.read_bytes() if settings_path.is_file() else None
    added = _add_hooks(settings)
    added.extend(_add_rules(settings, "ask", claude_settings.EXPECTED_ASK_RULES))
    added.extend(_add_allow_rules(settings))
    if not added:
        return "settings: already wired ({})".format(settings_path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        settings_path.with_name(settings_path.name + ".bak").write_bytes(original)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return "\n".join(added)
