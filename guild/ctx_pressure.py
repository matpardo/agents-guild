from guild import party_status
from guild.commands import statusline as statusline_commands

DEFAULT_HANDOFF_THRESHOLD = 80


def threshold(project_config):
    if project_config is None:
        return DEFAULT_HANDOFF_THRESHOLD
    configured = project_config.get("handoff_threshold")
    if configured is None:
        return DEFAULT_HANDOFF_THRESHOLD
    return configured


def is_high(pct, project_config):
    return pct >= threshold(project_config)


def reading(state_dir, session_id, project_config):
    pct = statusline_commands.read_ctx(state_dir, session_id)
    if pct is None:
        return None
    return {"pct": pct, "threshold": threshold(project_config), "high": is_high(pct, project_config)}


def for_party(ctx, party_row, project_config):
    if not party_status.has_live_leader(ctx, party_row):
        return None
    return reading(ctx.state_dir, party_row["leader_session_id"], project_config)
