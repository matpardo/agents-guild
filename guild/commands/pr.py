from guild import config, db, events, identity, refs
from guild.adapters import github
from guild.errors import GuildError

_TRACK_INITIAL_LIFECYCLE = "draft"
_DRAFT_READY_HINT = (
    "PR is draft on GitHub; mark it ready there (gh pr ready {}) or the next sync reverts it"
)


def _load_pr(ctx, repo, number):
    row = ctx.conn.execute(
        "SELECT * FROM prs WHERE repo = ? AND number = ?", (repo, number)
    ).fetchone()
    if row is None:
        raise GuildError("PR '{}#{}' is not tracked".format(repo, number), 1)
    return row


def track(ctx, ref, task_ref, what, waits, needs_human_pr_review):
    repo, number = refs.parse_pr_ref(ref)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    if repo not in project_data["github"]["repos"]:
        raise GuildError(
            "repo '{}' is not in project '{}' github.repos".format(repo, project), 1
        )
    quest, tid = refs.parse_task_ref(task_ref)
    task_row = ctx.conn.execute(
        "SELECT quest FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if task_row is None:
        raise GuildError("unknown task '{}/{}'".format(quest, tid), 1)
    existing = ctx.conn.execute(
        "SELECT repo FROM prs WHERE repo = ? AND number = ?", (repo, number)
    ).fetchone()
    if existing is not None:
        raise GuildError("PR '{}#{}' is already tracked".format(repo, number), 1)
    try:
        gh_data = github.pr_view(ctx.cwd, repo, number, ["state", "isDraft", "headRefName", "title"])
    except github.GhCommandError as error:
        raise GuildError("gh pr view failed for '{}#{}': {}".format(repo, number, error), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "pr.tracked",
            "guild",
            {
                "repo": repo,
                "number": number,
                "party": binding["party"],
                "task_quest": quest,
                "task_tid": tid,
                "what": what,
                "waits": waits,
                "lifecycle": _TRACK_INITIAL_LIFECYCLE,
                "needs_human_pr_review": int(needs_human_pr_review),
                "branch": gh_data.get("headRefName"),
                "title": gh_data.get("title"),
                "gh_state": gh_data.get("state"),
                "gh_draft": gh_data.get("isDraft"),
                "seeded": 0,
            },
        )
    return "PR '{}#{}' tracked".format(repo, number)


def acknowledge_comments(ctx, repo, number):
    row = _load_pr(ctx, repo, number)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            row["party"],
            ctx.session_id,
            None,
            "pr.comments_acknowledged",
            "guild",
            {"repo": repo, "number": number},
        )


def _flag_value(requested, current):
    if requested is None:
        return int(current or 0)
    return int(requested)


def set_(ctx, ref, lifecycle, waits, needs_ask_answer, needs_human_pr_review):
    if all(option is None for option in (lifecycle, waits, needs_ask_answer, needs_human_pr_review)):
        raise GuildError(
            "pr set needs at least one of --lifecycle, --waits, --needs-ask-answer/--no-needs-ask-answer,"
            " --needs-human-pr-review/--no-needs-human-pr-review",
            1,
        )
    repo, number = refs.parse_pr_ref(ref)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = _load_pr(ctx, repo, number)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    new_lifecycle = lifecycle if lifecycle is not None else row["lifecycle"]
    new_waits = waits if waits is not None else row["waits"]
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "pr.set",
            "guild",
            {
                "repo": repo,
                "number": number,
                "lifecycle": new_lifecycle,
                "waits": new_waits,
                "needs_ask_answer": _flag_value(needs_ask_answer, row["needs_ask_answer"]),
                "needs_human_pr_review": _flag_value(needs_human_pr_review, row["needs_human_pr_review"]),
            },
        )
    message = "PR '{}#{}' updated".format(repo, number)
    if new_lifecycle == "ready" and row["gh_draft"]:
        return message + "\n" + _DRAFT_READY_HINT.format(number)
    return message
