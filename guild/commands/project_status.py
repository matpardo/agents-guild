from guild import config, timeutil
from guild.commands import finding as finding_commands
from guild.commands import merge_queue as merge_queue_commands

_SYNC_KINDS = {"sdd": "epic.synced", "tracker": "tracker.synced"}


def _age(conn, now, project, kind):
    row = conn.execute("SELECT MAX(ts) AS ts FROM events WHERE project = ? AND kind = ?", (project, kind)).fetchone()
    if row["ts"] is None:
        return None
    return timeutil.age_label(now, row["ts"])


def project_model(ctx, project, caps):
    project_data = config.load_project(ctx.projects_dir, project)
    file_cap = project_data.get("max_open_prs_per_file")
    hot_files = []
    if file_cap is not None:
        hot_files = merge_queue_commands.hot_files(ctx.conn, project_data["github"]["repos"], file_cap)
    return {
        "name": project,
        "open_prs": caps["project_open"],
        "max_open_prs": caps["project_cap"],
        "wait": caps["project_wait"],
        "hot_files": hot_files,
        "finding_classes": finding_commands.class_models(
            ctx.conn, project, project_data.get("finding_guard_threshold")
        ),
        "freshness": {name: _age(ctx.conn, ctx.now, project, kind) for name, kind in _SYNC_KINDS.items()},
    }


def freshness_text(freshness):
    return ", ".join(
        "{} synced {}".format(name, "never" if age is None else "{} ago".format(age)) for name, age in freshness.items()
    )


def project_lines(model):
    lines = []
    if model["max_open_prs"] is not None:
        lines.append("  open PRs: {}/{}".format(model["open_prs"], model["max_open_prs"]))
    if model["wait"] is not None:
        lines.append("  {}".format(model["wait"]))
    for hot in model["hot_files"]:
        lines.append("  hot file: {} {}: {}".format(hot["repo"], hot["path"], ", ".join(hot["prs"])))
    for entry in model["finding_classes"]:
        marker = " (at threshold)" if entry["at_threshold"] else ""
        lines.append("  finding class: {} {} PR(s){}".format(entry["class"], entry["count"], marker))
    lines.append("  " + freshness_text(model["freshness"]))
    return lines
