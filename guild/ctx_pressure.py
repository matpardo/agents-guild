from guild import party_status
from guild.commands import statusline as statusline_commands

DEFAULT_HANDOFF_THRESHOLD = 80


def _configured(project_config):
    if project_config is None:
        return DEFAULT_HANDOFF_THRESHOLD
    configured = project_config.get("handoff_threshold")
    if configured is None:
        return DEFAULT_HANDOFF_THRESHOLD
    return configured


def threshold(state_dir, global_config, project_config):
    margin = global_config.get("handoff_margin")
    compaction = statusline_commands.latest_compact_pct(state_dir)
    if margin is None or compaction is None:
        return {"value": _configured(project_config), "source": "configured"}
    return {"value": max(compaction - margin, 0), "source": "compaction {}% − {}".format(compaction, margin)}


def reading(state_dir, session_id, global_config, project_config):
    pct = statusline_commands.read_ctx(state_dir, session_id)
    if pct is None:
        return None
    resolved = threshold(state_dir, global_config, project_config)
    return {"pct": pct, "threshold": resolved["value"], "source": resolved["source"], "high": pct >= resolved["value"]}


def for_party(ctx, party_row, global_config, project_config):
    if not party_status.has_live_leader(ctx, party_row):
        return None
    return reading(ctx.state_dir, party_row["leader_session_id"], global_config, project_config)
