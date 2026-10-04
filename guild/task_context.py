from pathlib import Path

from guild import config
from guild.errors import GuildError


def project_config(ctx, party):
    row = ctx.conn.execute("SELECT project FROM parties WHERE name = ?", (party,)).fetchone()
    if row is None or row["project"] is None:
        return None, None
    try:
        return row["project"], config.load_project(ctx.projects_dir, row["project"])
    except GuildError:
        return row["project"], None


def _sdd_path(sdd_config, epic, file_name):
    if sdd_config is None or epic is None:
        return None
    epics_dir = sdd_config.get("epics_dir")
    if epics_dir is None:
        return None
    if "root" in sdd_config:
        return str(Path(sdd_config["root"]).expanduser() / epics_dir / epic / file_name)
    if "git_ref" in sdd_config:
        return "git:{}:{}".format(sdd_config["git_ref"], "{}/{}/{}".format(epics_dir, epic, file_name))
    return None


def sdd_paths(project_config, epic):
    sdd_config = None if project_config is None else project_config.get("sdd")
    return _sdd_path(sdd_config, epic, "spec.md"), _sdd_path(sdd_config, epic, "tasks.md")


def task_ref(ctx, project_config, ref):
    quest, tid = ref[len("task:"):].split("/", 1)
    row = ctx.conn.execute(
        "SELECT quest_tasks.title AS title, quest_tasks.state AS state, quests.epic AS epic"
        " FROM quest_tasks LEFT JOIN quests ON quests.slug = quest_tasks.quest"
        " WHERE quest_tasks.quest = ? AND quest_tasks.tid = ?",
        (quest, tid),
    ).fetchone()
    if row is None:
        return {"kind": "task", "ref": ref, "quest": quest, "tid": tid, "missing": True}
    spec, tasks = sdd_paths(project_config, row["epic"])
    return {
        "kind": "task",
        "ref": ref,
        "quest": quest,
        "tid": tid,
        "title": row["title"],
        "state": row["state"],
        "epic": row["epic"],
        "spec": spec,
        "tasks": tasks,
    }
