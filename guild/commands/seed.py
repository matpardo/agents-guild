import json
from pathlib import Path

from guild import db, events, timeutil
from guild.errors import GuildError
from guild.ids import next_id

_TASK_KIND_FOR_STATE = {"active": "task.started", "blocked": "task.blocked", "done": "task.done"}


def _seed_party(ctx, party):
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        party["name"],
        None,
        party.get("project"),
        "party.started",
        "local",
        {"party": party["name"], "session_name": party.get("session_name")},
    )


def _seed_quest(ctx, quest):
    tasks = quest.get("tasks", [])
    task_entries = [{"tid": task["tid"], "title": task.get("title", task["tid"])} for task in tasks]
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        quest["party"],
        None,
        quest.get("project"),
        "quest.added",
        "local",
        {
            "slug": quest["slug"],
            "project": quest.get("project"),
            "party": quest["party"],
            "epic": quest.get("epic"),
            "title": quest["title"],
            "tasks": task_entries,
        },
    )
    for task in tasks:
        state = task.get("state", "queued")
        if state == "queued":
            continue
        kind = _TASK_KIND_FOR_STATE.get(state)
        if kind is None:
            raise GuildError("invalid seed task state '{}'".format(state), 1)
        payload = {"quest": quest["slug"], "tid": task["tid"]}
        if kind == "task.blocked":
            payload["reason"] = task.get("reason", "")
        else:
            payload["summary"] = task.get("summary")
        events.record(
            ctx.conn, ctx.now, ctx.origin, quest["party"], None, quest.get("project"), kind, "local", payload
        )


def _seed_pr(ctx, pr):
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        pr["party"],
        None,
        pr.get("project"),
        "pr.tracked",
        "guild",
        {
            "repo": pr["repo"],
            "number": pr["number"],
            "party": pr["party"],
            "task_quest": pr.get("task_quest"),
            "task_tid": pr.get("task_tid"),
            "card": pr.get("card"),
            "what": pr["what"],
            "waits": pr.get("waits"),
            "lifecycle": pr.get("lifecycle", "draft"),
            "needs_ask_answer": pr.get("needs_ask_answer", False),
            "needs_human_pr_review": pr.get("needs_human_pr_review", False),
            "fixes_main": pr.get("fixes_main", False),
            "fixes_flaky": pr.get("fixes_flaky", False),
            "branch": pr.get("branch"),
            "title": pr.get("title"),
            "gh_state": pr.get("gh_state"),
            "gh_draft": pr.get("gh_draft"),
            "seeded": 1,
        },
    )


def _seed_ask(ctx, ask):
    ask_id = next_id(ctx.conn, "asks")
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        ask["party"],
        None,
        ask.get("project"),
        "ask.created",
        "local",
        {
            "id": ask_id,
            "party": ask["party"],
            "question": ask["question"],
            "context": ask.get("context", ""),
            "refs": ask.get("refs", []),
            "options": ask.get("options", []),
        },
    )


def _seed_notice(ctx, notice):
    notice_id = next_id(ctx.conn, "notices")
    expires_at = timeutil.expires_at_iso(ctx.now, notice["ttl"])
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        notice.get("party"),
        None,
        notice.get("project"),
        "notice.created",
        "guild",
        {
            "id": notice_id,
            "party": notice.get("party"),
            "scope": notice["scope"],
            "text": notice["text"],
            "until_condition": notice.get("until"),
            "expires_at": expires_at,
            "announces": notice.get("announces"),
        },
    )


def run(ctx, file_path):
    path = Path(file_path)
    if not path.is_file():
        raise GuildError("seed file '{}' does not exist".format(file_path), 1)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise GuildError("invalid JSON in '{}': {}".format(file_path, error), 1) from error
    with db.writing(ctx.conn):
        for party in data.get("parties", []):
            _seed_party(ctx, party)
        for quest in data.get("quests", []):
            _seed_quest(ctx, quest)
        for pr in data.get("prs", []):
            _seed_pr(ctx, pr)
        for ask in data.get("asks", []):
            _seed_ask(ctx, ask)
        for notice in data.get("notices", []):
            _seed_notice(ctx, notice)
    return "seed '{}' loaded".format(file_path)
