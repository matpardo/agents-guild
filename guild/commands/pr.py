from guild import config, db, events, identity, merge_queue, polling, refs, sanitize
from guild.adapters import github
from guild.commands import main_status as main_status_commands
from guild.commands import merge_queue as merge_queue_commands
from guild.errors import GuildError

_CLOSED_LIFECYCLES = ("merged", "closed")
_TRACK_INITIAL_LIFECYCLE = "draft"
_DRAFT_READY_HINT = (
    "PR is draft on GitHub; mark it ready there (gh pr ready {}) or the next sync reverts it"
)


def _load_pr(conn, repo, number):
    row = conn.execute(
        "SELECT * FROM prs WHERE repo = ? AND number = ?", (repo, number)
    ).fetchone()
    if row is None:
        raise GuildError("PR '{}#{}' is not tracked".format(repo, number), 1)
    return row


def _task_fields(ctx, task_ref):
    if task_ref is None:
        return None, None
    quest, tid = refs.parse_task_ref(task_ref)
    task_row = ctx.conn.execute(
        "SELECT quest FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if task_row is None:
        raise GuildError("unknown task '{}/{}'".format(quest, tid), 1)
    return quest, tid


def _adventurer_work(adventurer, task_ref, card):
    if adventurer["task"] is not None:
        if task_ref == adventurer["task"]:
            return
        raise GuildError("an adventurer on a task tracks PRs with --task equal to its own task", 1)
    if card is not None and task_ref is None:
        return
    raise GuildError("an adventurer with a free job tracks PRs with --card alone", 1)


def _tracking_fields(ctx, task_ref, card):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        binding = identity.require_binding(ctx.conn, ctx.session_id)
        if task_ref is None:
            raise GuildError(
                "a party's PR belongs to one of its tasks: add one with `guild task add <quest>/<tid>` "
                "or `guild quest add <slug> --no-epic`",
                1,
            )
        quest, tid = _task_fields(ctx, task_ref)
        return binding["party"], binding["party"], None, quest, tid
    _adventurer_work(adventurer, task_ref, card)
    return "", None, adventurer["id"], None, None


def track(ctx, ref, task_ref, card, what, waits, needs_human_pr_review, fixes_main, fixes_flaky):
    repo, number = refs.parse_pr_ref(ref)
    party, actor_party, adventurer_id, quest, tid = _tracking_fields(ctx, task_ref, card)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    if repo not in project_data["github"]["repos"]:
        raise GuildError(
            "repo '{}' is not in project '{}' github.repos".format(repo, project), 1
        )
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
            actor_party,
            ctx.session_id,
            project,
            "pr.tracked",
            "guild",
            {
                "repo": repo,
                "number": number,
                "party": party,
                "adventurer": adventurer_id,
                "task_quest": quest,
                "task_tid": tid,
                "card": card,
                "what": what,
                "waits": waits,
                "lifecycle": _TRACK_INITIAL_LIFECYCLE,
                "needs_human_pr_review": int(needs_human_pr_review),
                "fixes_main": int(fixes_main),
                "fixes_flaky": int(fixes_flaky),
                "branch": gh_data.get("headRefName"),
                "title": gh_data.get("title"),
                "gh_state": gh_data.get("state"),
                "gh_draft": gh_data.get("isDraft"),
                "seeded": 0,
            },
        )
    return "PR '{}#{}' tracked".format(repo, number)


def acknowledge_comments(ctx, repo, number):
    row = _load_pr(ctx.conn, repo, number)
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


def _blocked_external_value(blocked_external, no_blocked_external, current):
    if no_blocked_external:
        return None
    if blocked_external is None:
        return current
    if not blocked_external.strip():
        raise GuildError("--blocked-external needs a reason", 1)
    return blocked_external.strip()


def _current_fields(row):
    return {
        "lifecycle": row["lifecycle"],
        "waits": row["waits"],
        "needs_ask_answer": int(row["needs_ask_answer"] or 0),
        "needs_human_pr_review": int(row["needs_human_pr_review"] or 0),
        "fixes_main": int(row["fixes_main"] or 0),
        "fixes_flaky": int(row["fixes_flaky"] or 0),
        "blocked_external": row["blocked_external"],
    }


def _record_pr_set(ctx, actor, project, repo, number, fields):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor,
            ctx.session_id,
            project,
            "pr.set",
            "guild",
            dict(fields, repo=repo, number=number),
        )


def _set_blocked_external_as_human(ctx, ref, reason):
    repo, number = refs.parse_pr_ref(ref)
    row = _load_pr(ctx.conn, repo, number)
    fields = _current_fields(row)
    fields["blocked_external"] = reason
    _record_pr_set(ctx, None, merge_queue_commands._project_for_repo(ctx, repo), repo, number, fields)
    return "PR '{}#{}' updated".format(repo, number)


def block_external(ctx, ref, reason):
    if not reason.strip():
        raise GuildError("a reason is required", 1)
    return _set_blocked_external_as_human(ctx, ref, reason.strip())


def unblock_external(ctx, ref):
    return _set_blocked_external_as_human(ctx, ref, None)


def set_(
    ctx, ref, lifecycle, waits, needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky,
    blocked_external, no_blocked_external,
):
    options = (lifecycle, waits, needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky, blocked_external)
    if all(option is None for option in options) and not no_blocked_external:
        raise GuildError(
            "pr set needs at least one of --lifecycle, --waits, --needs-ask-answer/--no-needs-ask-answer,"
            " --needs-human-pr-review/--no-needs-human-pr-review,"
            " --fixes-main/--no-fixes-main, --fixes-flaky/--no-fixes-flaky,"
            " --blocked-external/--no-blocked-external",
            1,
        )
    repo, number = refs.parse_pr_ref(ref)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = _load_pr(ctx.conn, repo, number)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    fields = _current_fields(row)
    fields["lifecycle"] = lifecycle if lifecycle is not None else row["lifecycle"]
    fields["waits"] = waits if waits is not None else row["waits"]
    fields["needs_ask_answer"] = _flag_value(needs_ask_answer, row["needs_ask_answer"])
    fields["needs_human_pr_review"] = _flag_value(needs_human_pr_review, row["needs_human_pr_review"])
    fields["fixes_main"] = _flag_value(fixes_main, row["fixes_main"])
    fields["fixes_flaky"] = _flag_value(fixes_flaky, row["fixes_flaky"])
    fields["blocked_external"] = _blocked_external_value(blocked_external, no_blocked_external, row["blocked_external"])
    _record_pr_set(ctx, binding["party"], project, repo, number, fields)
    new_lifecycle = fields["lifecycle"]
    message = "PR '{}#{}' updated".format(repo, number)
    if new_lifecycle == "ready" and row["gh_draft"]:
        return message + "\n" + _DRAFT_READY_HINT.format(number)
    return message


def ready_check(ctx, ref):
    repo, number = refs.parse_pr_ref(ref)
    row = _load_pr(ctx.conn, repo, number)
    if row["lifecycle"] in _CLOSED_LIFECYCLES:
        raise GuildError("PR '{}' is {}: nothing left to merge".format(ref, row["lifecycle"]), 1)
    records = merge_queue_commands.open_pr_records(ctx.conn)
    red_rows = main_status_commands.red_rows(ctx.conn)
    queue = merge_queue.compute(records, merge_queue_commands.load_pins(ctx.conn), red_rows)["queue"]
    ref_text = "{}#{}".format(repo, number)
    entry = next(entry for entry in queue if entry["ref"] == ref_text)
    gates = merge_queue_commands.gates(entry, red_rows)
    lines = ["{} {}".format(ref_text, entry["human_state"])]
    lines.extend("- {}".format(blocker) for blocker in entry["blockers"])
    lines.extend("- {}".format(text) for text in entry["human_missing"])
    lines.extend("- wait: {}".format(wait) for wait in entry["waits"])
    lines.extend("- gate: {}".format(gate) for gate in gates)
    lines.extend("- note: {}".format(note) for note in merge_queue_commands.notes(ctx.projects_dir, entry, red_rows))
    ready = entry["action"] == "merge" and entry["human_state"] in merge_queue.HUMAN_READY_STATES
    exit_code = 0 if ready and not gates else 1
    return [sanitize.strip_control_sequences(line) for line in lines], exit_code


_STALE_SECONDS = 1800


class _PrWatch:
    def __init__(self, ref, started_at):
        self._ref = ref
        self._baseline = None
        self._seen_pending = False
        self._synced_at = None
        self._changed_at = started_at

    def check(self, row, now):
        closed = self._closed_line(row)
        if closed is not None:
            return closed, 0
        if self._new_discussion(row["other_author_comments"]):
            return "{} new comment or review".format(self._ref), 0
        if self._checks_finished(row):
            return "{} checks finished: {} failing, {} passing".format(
                self._ref, row["checks_failing"] or 0, row["checks_passing"] or 0
            ), 0
        if self._stale(row["synced_at"], now):
            return (
                "{}: no sync for 30m: run guild sync --source gh or install guild sync-timer".format(self._ref),
                4,
            )
        return None

    def _closed_line(self, row):
        if row["lifecycle"] in _CLOSED_LIFECYCLES:
            return "{} {}".format(self._ref, row["lifecycle"])
        return None

    def _new_discussion(self, current):
        if current is None:
            return False
        baseline = self._baseline
        self._baseline = current if baseline is None else min(baseline, current)
        return baseline is not None and current > baseline

    def _checks_finished(self, row):
        pending = row["checks_pending"]
        if pending:
            self._seen_pending = True
        return self._seen_pending and pending == 0

    def _stale(self, synced_at, now):
        if synced_at != self._synced_at:
            self._synced_at = synced_at
            self._changed_at = now
            return False
        return (now - self._changed_at).total_seconds() > _STALE_SECONDS


def _read_pr(conn, repo, number):
    row = conn.execute(
        "SELECT lifecycle, other_author_comments, checks_pending, checks_failing, checks_passing, synced_at"
        " FROM prs WHERE repo = ? AND number = ?",
        (repo, number),
    ).fetchone()
    if row is None:
        raise GuildError("PR '{}#{}' is no longer tracked".format(repo, number), 1)
    return row


def wait(conn, ref, timeout, sleep, clock):
    repo, number = refs.parse_pr_ref(ref)
    if _load_pr(conn, repo, number)["other_author_comments"] is None:
        raise GuildError("no sync data yet for {}: run guild sync --source gh first".format(ref), 1)
    watch = _PrWatch(ref, clock())
    result = polling.until(
        lambda: _read_pr(conn, repo, number),
        lambda row: watch.check(row, clock()),
        timeout,
        sleep,
        clock,
    )
    if result is None:
        return "{} no change in {}".format(ref, polling.timeout_label(timeout)), 3
    return result
