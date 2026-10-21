import json
import shlex
import textwrap

from guild import config, ctx_pressure, identity, links, merge_queue, party_progress, party_status, party_waits, pii, pr_asks, resume
from guild import paths, sanitize, session_status, timeutil
from guild.commands import brief as brief_commands
from guild.commands import claim as claim_commands
from guild.commands import drift as drift_commands
from guild.commands import idea as idea_commands
from guild.commands import memory as memory_commands
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import next as next_commands
from guild.commands import notice as notice_commands
from guild.commands import project_status
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_ANSWERED_PAGE_SIZE = 10

_STYLES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
    "magenta": "35",
}

_FLAG_STYLES = (
    ("fixes_main", "fixes-main", "red"),
    ("fixes_flaky", "fixes-flaky", "cyan"),
    ("needs_ask_answer", "needs-ask-answer", "red"),
    ("needs_human_pr_review", "needs-human-pr-review", "yellow"),
    ("blocked_external", "blocked-external", "yellow"),
)


_STATUS_STYLES = {
    "waiting-permission": "red",
    "waiting-ask": "yellow",
    "waiting-input": "yellow",
    "stopped-with-work": "cyan",
    "working": "green",
    "done": "dim",
    "unknown": "dim",
    "idle": "dim",
    "queued": "cyan",
    "closed": "dim",
}

_LIFECYCLE_STYLES = {
    "converging": "yellow",
    "ready": "green",
    "draft": "dim",
    "merged": "magenta",
    "closed": "dim",
}


class _Painter:
    def __init__(self, color, width):
        self.color = color
        self.width = width

    def paint(self, text, style):
        text = sanitize.strip_control_sequences(text)
        if not self.color:
            return text
        return "\033[{}m{}\033[0m".format(_STYLES[style], text)

    def wrap(self, text, indent):
        text = sanitize.strip_control_sequences(text)
        return textwrap.wrap(
            text,
            width=max(self.width, 40),
            initial_indent=indent,
            subsequent_indent=indent,
            break_on_hyphens=False,
        )


def _checks_parts(pr_row):
    failing = pr_row["checks_failing"] or 0
    passing = pr_row["checks_passing"] or 0
    pending = pr_row["checks_pending"] or 0
    if failing == 0 and passing == 0 and pending == 0:
        return None
    return failing, passing, pending


def _checks_plain(pr_row):
    parts = _checks_parts(pr_row)
    if parts is None:
        return "no checks"
    text = "✗{} ✓{}".format(parts[0], parts[1])
    if parts[2] > 0:
        return "{} ⏳{}".format(text, parts[2])
    return text


def _checks_painted(painter, pr_row):
    parts = _checks_parts(pr_row)
    if parts is None:
        return painter.paint("no checks", "dim")
    failing_style = "red" if parts[0] > 0 else "dim"
    text = "{} {}".format(
        painter.paint("✗{}".format(parts[0]), failing_style),
        painter.paint("✓{}".format(parts[1]), "green"),
    )
    if parts[2] > 0:
        return "{} {}".format(text, painter.paint("⏳{}".format(parts[2]), "yellow"))
    return text


def _badges(ctx, pr_row):
    badges = [(pr_row["lifecycle"], _LIFECYCLE_STYLES[pr_row["lifecycle"]])]
    for column, label, style in _FLAG_STYLES:
        if column == "needs_ask_answer" and pr_row["open_ask_id"] is not None:
            badges.append(("{} (ask #{})".format(label, pr_row["open_ask_id"]), style))
        elif pr_row[column]:
            badges.append((label, style))
    return badges


def _visible_waits(pr_row):
    if pr_row["lifecycle"] in ("merged", "closed"):
        return None
    return pr_row["waits"]


def _card_prefix(pr_row):
    if pr_row["card"] is None:
        return ""
    return "{}  ".format(sanitize.strip_control_sequences(pr_row["card"]))


def _pr_lines(ctx, painter, pr_row, indent):
    badges = _badges(ctx, pr_row)
    status_plain = "{}  {}".format(" ".join(label for label, _ in badges), _checks_plain(pr_row))
    status_painted = "{}  {}".format(
        " ".join(painter.paint(label, style) for label, style in badges), _checks_painted(painter, pr_row)
    )
    plain_head = "● {}#{}  {}  {}{}".format(
        pr_row["repo"].split("/")[-1],
        pr_row["number"],
        status_plain,
        _card_prefix(pr_row),
        sanitize.strip_control_sequences(pr_row["what"]),
    )
    head_lines = textwrap.wrap(
        plain_head,
        width=max(painter.width, 40),
        initial_indent=indent,
        subsequent_indent=indent + "  ",
        break_on_hyphens=False,
    )
    head_lines[0] = head_lines[0].replace(status_plain, status_painted, 1)
    branch = _optional_text(pr_row["branch"])
    if branch is not None:
        branch_lines = painter.wrap("branch: {}".format(branch), indent + "  ")
        head_lines = head_lines + [painter.paint(line, "dim") for line in branch_lines]
    waits = _visible_waits(pr_row)
    if not waits:
        return head_lines
    return head_lines + painter.wrap("waits: {}".format(waits), indent + "  ")


def _pr_ref_blocked(conn, ref):
    repo, number = ref[len("pr:"):].rsplit("#", 1)
    row = conn.execute(
        "SELECT lifecycle FROM prs WHERE repo = ? AND number = ?", (repo, int(number))
    ).fetchone()
    if row is None:
        return True
    return row["lifecycle"] not in ("merged", "closed")


def _task_ref_blocked(conn, ref):
    quest, tid = ref[len("task:"):].split("/", 1)
    row = conn.execute(
        "SELECT state FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if row is None:
        return True
    return row["state"] != "done"


def _blocked_ref_count(conn, ref_list):
    count = 0
    for ref in ref_list:
        if ref.startswith("card:"):
            continue
        blocked = _pr_ref_blocked(conn, ref) if ref.startswith("pr:") else _task_ref_blocked(conn, ref)
        if blocked:
            count += 1
    return count


def _ask_detail_lines(painter, conn, row):
    ref_list = json.loads(row["refs"])
    blocked_count = _blocked_ref_count(conn, ref_list)
    lines = [
        "  {} {} · {}".format(
            painter.paint("#{}".format(row["id"]), "red"),
            painter.paint(row["party"], "cyan"),
            painter.paint(row["question"], "bold"),
        )
    ]
    lines.extend(painter.paint(line, "dim") for line in painter.wrap(row["context"], "     "))
    option_list = json.loads(row["options"])
    if option_list:
        lines.append("     options: {}".format(" | ".join(option_list)))
    lines.append(painter.paint("     refs: {}".format(", ".join(ref_list)), "dim"))
    if blocked_count > 0:
        blocks_text = "blocks: {} of {} refs still open".format(blocked_count, len(ref_list))
    else:
        blocks_text = "blocks: 0 of {} refs still open (may be stale)".format(len(ref_list))
    lines.append(painter.paint("     {}".format(blocks_text), "dim"))
    lines.append(painter.paint('     → guild answer {} "..."'.format(row["id"]), "dim"))
    lines.append("")
    return lines


def _ask_summary_lines(painter, conn, row):
    ref_list = json.loads(row["refs"])
    blocked_count = _blocked_ref_count(conn, ref_list)
    option_list = json.loads(row["options"])
    options_text = "  [{}]".format(" | ".join(option_list)) if option_list else ""
    blocks_text = "  · blocks {}".format(blocked_count) if blocked_count > 0 else ""
    wrapped = painter.wrap(
        "{} · {}{}{}".format(row["party"], row["question"], options_text, blocks_text), "      "
    )
    first = "  {} {}".format(painter.paint("#{}".format(row["id"]), "red"), wrapped[0].strip())
    return [first] + wrapped[1:]


def _sorted_open_asks(conn, party_names):
    rows = conn.execute("SELECT * FROM asks WHERE state = 'open' ORDER BY id ASC").fetchall()
    if party_names is not None:
        rows = [row for row in rows if row["party"] in party_names]
    return rows


def _needs_you_heading(ask_count, blocked_count, ctx_high_count):
    parts = []
    if ask_count:
        parts.append("{} {}".format(ask_count, "open ask" if ask_count == 1 else "open asks"))
    if blocked_count:
        parts.append("{} blocked".format(blocked_count))
    if ctx_high_count:
        parts.append("{} context high".format(ctx_high_count))
    return "NEEDS YOU · {}".format(" · ".join(parts))


def _blocked_line(ctx, painter, row):
    status = {"status": "waiting-permission", "since": row["since"], "detail": row["detail"]}
    text = "  ⏸ {} {}".format(row["party"], party_status.label(ctx, status))
    if row["detail"]:
        text = '{}: "{}"'.format(text, row["detail"])
    return painter.paint(text, "red")


def _ctx_high_parties(ctx, party_names):
    party_rows = ctx.conn.execute("SELECT * FROM parties WHERE state != 'closed'").fetchall()
    projects_by_name = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    names_over_threshold = []
    for party_row in party_rows:
        if party_names is not None and party_row["name"] not in party_names:
            continue
        pressure = _ctx_model(ctx, party_row, projects_by_name.get(party_row["project"]))
        if pressure is not None and pressure["high"]:
            names_over_threshold.append(party_row["name"])
    return names_over_threshold


def render_asks(ctx, party_names, color, width, detailed):
    painter = _Painter(color, width)
    rows = _sorted_open_asks(ctx.conn, party_names)
    blocked = session_status.blocked_rows(ctx.conn, party_names)
    ctx_high = _ctx_high_parties(ctx, party_names)
    if not rows and not blocked and not ctx_high:
        return [painter.paint("NEEDS YOU · nothing", "green"), ""]
    lines = [painter.paint(_needs_you_heading(len(rows), len(blocked), len(ctx_high)), "bold")]
    lines.extend(_blocked_line(ctx, painter, row) for row in blocked)
    if detailed:
        for row in rows:
            lines.extend(_ask_detail_lines(painter, ctx.conn, row))
        return lines
    for row in rows:
        lines.extend(_ask_summary_lines(painter, ctx.conn, row))
    if rows:
        lines.append(painter.paint('  → guild asks (context) · guild answer <id> "..."', "dim"))
    lines.append("")
    return lines


def _all_ask_rows(conn, party, since_cutoff):
    rows = conn.execute("SELECT * FROM asks ORDER BY id ASC").fetchall()
    if party is not None:
        rows = [row for row in rows if row["party"] == party]
    if since_cutoff is not None:
        rows = [row for row in rows if timeutil.from_iso(row["created_at"]) >= since_cutoff]
    return rows


def _all_asks_heading(rows):
    counts = {"open": 0, "answered": 0, "dismissed": 0}
    for row in rows:
        counts[row["state"]] += 1
    return "ASKS · {} ({} open · {} answered · {} dismissed)".format(
        len(rows), counts["open"], counts["answered"], counts["dismissed"]
    )


def _all_ask_lines(painter, row):
    state_style = {"open": "red", "answered": "green", "dismissed": "dim"}[row["state"]]
    lines = [
        "  {} {} · {} · {}".format(
            painter.paint("#{}".format(row["id"]), "red"),
            painter.paint(row["party"], "cyan"),
            painter.paint(row["state"], state_style),
            painter.paint(row["question"], "bold"),
        )
    ]
    if row["state"] != "answered":
        return lines
    lines.extend(painter.wrap("answer: {}".format(row["answer"]), "     "))
    if row["answered_at"] is not None:
        lines.append("     answered: {}".format(timeutil.issued_label(row["answered_at"])))
    return lines


def render_all_asks(ctx, party, since_cutoff, color, width):
    painter = _Painter(color, width)
    _check_party_known(ctx.conn, party)
    rows = _all_ask_rows(ctx.conn, party, since_cutoff)
    if not rows:
        return [painter.paint("ASKS · nothing", "green"), ""]
    lines = [painter.paint(_all_asks_heading(rows), "bold")]
    for row in rows:
        lines.extend(_all_ask_lines(painter, row))
    lines.append("")
    return lines


def _answered_ask_rows(conn, party, since_cutoff):
    rows = [row for row in _all_ask_rows(conn, party, since_cutoff) if row["state"] == "answered"]
    return sorted(rows, key=lambda row: (row["answered_at"] or "", row["id"]), reverse=True)


def _check_party_known(conn, party):
    if party is None:
        return
    if conn.execute("SELECT name FROM parties WHERE name = ?", (party,)).fetchone() is None:
        raise GuildError("unknown party '{}'".format(party), 1)


def _answered_page(conn, party, since_cutoff, page):
    _check_party_known(conn, party)
    rows = _answered_ask_rows(conn, party, since_cutoff)
    if not rows:
        return [], 0, 0
    page_count = -(-len(rows) // _ANSWERED_PAGE_SIZE)
    if page < 1 or page > page_count:
        raise GuildError("page {} out of range, 1-{}".format(page, page_count), 1)
    start = (page - 1) * _ANSWERED_PAGE_SIZE
    return rows[start : start + _ANSWERED_PAGE_SIZE], len(rows), page_count


def render_answered_asks(ctx, party, since_cutoff, page, color, width):
    painter = _Painter(color, width)
    page_rows, total, page_count = _answered_page(ctx.conn, party, since_cutoff, page)
    if total == 0:
        return [painter.paint("ANSWERED · nothing", "green"), ""]
    lines = [painter.paint("ANSWERED · {} · page {}/{}".format(total, page, page_count), "bold")]
    for row in page_rows:
        lines.extend(_all_ask_lines(painter, row))
    if page < page_count:
        lines.append(painter.paint("  → guild asks --answered --page {}".format(page + 1), "dim"))
    lines.append("")
    return lines


def answered_asks_model(conn, page):
    page_rows, total, page_count = _answered_page(conn, None, None, page)
    return {
        "page": page,
        "page_count": page_count,
        "total": total,
        "asks": [_answered_ask_model(row) for row in page_rows],
    }


def _answered_ask_model(row):
    return {
        "id": row["id"],
        "party": row["party"],
        "question": sanitize.strip_control_sequences(row["question"]),
        "answer": _optional_text(row["answer"]),
        "answered_at": row["answered_at"],
        "answered": _answered_label(row["answered_at"]),
    }


def _answered_label(answered_at):
    if answered_at is None:
        return None
    return timeutil.issued_label(answered_at)


def _party_scoped_notices(ctx, party_filter):
    rows = notice_commands.active_notices(ctx.conn, ctx.now)
    if party_filter is None:
        return rows
    return [row for row in rows if row["party"] == party_filter]


def _raid_scoped_notices(ctx, raid_name):
    scope = "raid:{}".format(raid_name)
    return [row for row in notice_commands.active_notices(ctx.conn, ctx.now) if row["scope"] == scope]


def _notice_flagged(row):
    author = identity.actor_label(row["party"], bool(row["unbound"]))
    return author != identity.HUMAN_LABEL and pii.looks_instruction_like(row["text"])


def _notices_section(ctx, painter, rows):
    if not rows:
        return []
    new_count = notice_commands.count_new(rows)
    header = "NOTICES · {} active".format(len(rows))
    if new_count > 0:
        header = "{} ({} new)".format(header, new_count)
    lines = [painter.paint(header, "bold")]
    for row in rows:
        marker = painter.paint("new", "green") + " " if notice_commands.is_new(row) else ""
        flag = " " + painter.paint("flagged", "red") if _notice_flagged(row) else ""
        lines.append(
            "  {}{} {}{} · {}".format(
                marker,
                painter.paint("#{}".format(row["id"]), "yellow"),
                painter.paint(identity.actor_label(row["party"], bool(row["unbound"])), "cyan"),
                flag,
                painter.paint(
                    "{} · {} · {}".format(
                        timeutil.issued_label(row["created_at"]),
                        row["scope"],
                        timeutil.time_left_label(ctx.now, row["expires_at"]),
                    ),
                    "dim",
                ),
            )
        )
        lines.extend(painter.wrap(row["text"], "     "))
    lines.append("")
    return lines


def _task_lines(ctx, painter, task_row, task_prs):
    if task_row["state"] == "blocked":
        return [
            painter.paint(
                "    ■ blocked: {} — {}".format(task_row["tid"], task_row["blocked_reason"]), "red"
            )
        ]
    title = sanitize.strip_control_sequences(task_row["title"])
    lines = ["    ▶ {}  {}".format(painter.paint(task_row["tid"], "bold"), title)]
    if task_row["summary"]:
        lines.extend(painter.paint(line, "dim") for line in painter.wrap(task_row["summary"], "        "))
    for pr_row in task_prs:
        lines.extend(_pr_lines(ctx, painter, pr_row, "        "))
    return lines


def _open_task_rows(conn, quest_slug):
    return conn.execute(
        "SELECT * FROM quest_tasks WHERE quest = ? AND state != 'done' ORDER BY tid ASC",
        (quest_slug,),
    ).fetchall()


def _close_blockers(ctx, quest_row):
    if quest_row["epic"] is None:
        return None
    if _open_task_rows(ctx.conn, quest_row["slug"]):
        return None
    has_tasks = ctx.conn.execute(
        "SELECT 1 FROM quest_tasks WHERE quest = ? LIMIT 1", (quest_row["slug"],)
    ).fetchone()
    if has_tasks is None:
        return None
    split = drift_commands.epic_findings_by_owner(
        ctx.conn, quest_row["project"], quest_row["epic"], quest_row["party"]
    )
    if not split["own"] and not split["foreign"]:
        return None
    return split


def _close_blocker_lines(painter, blockers):
    summary = "    can't close: drift ({} yours, {} other parties)".format(
        len(blockers["own"]), len(blockers["foreign"])
    )
    lines = [painter.paint(summary, "red")]
    lines.extend("      yours: {}".format(text) for text in blockers["own"])
    lines.extend(
        "      other parties: {} (party {})".format(item["text"], item["party"])
        for item in blockers["foreign"]
    )
    return lines


def _quest_lines(ctx, painter, quest_row, prs_by_task):
    title = sanitize.strip_control_sequences(quest_row["title"])
    lines = ["  {} — {}".format(painter.paint(quest_row["slug"], "bold"), title)]
    task_rows = _open_task_rows(ctx.conn, quest_row["slug"])
    queued = []
    for task_row in task_rows:
        if task_row["state"] == "queued":
            queued.append(task_row["tid"])
            continue
        task_prs = prs_by_task.get((quest_row["slug"], task_row["tid"]), [])
        lines.extend(_task_lines(ctx, painter, task_row, task_prs))
    if queued:
        lines.append(painter.paint("    ○ queued: {}".format(", ".join(queued)), "dim"))
    blockers = _close_blockers(ctx, quest_row)
    if blockers is not None:
        lines.extend(_close_blocker_lines(painter, blockers))
    return lines


def _finished_with_task(ctx, pr_row):
    if pr_row["lifecycle"] not in ("merged", "closed"):
        return False
    task_row = ctx.conn.execute(
        "SELECT state FROM quest_tasks WHERE quest = ? AND tid = ?",
        (pr_row["task_quest"], pr_row["task_tid"]),
    ).fetchone()
    return task_row is None or task_row["state"] == "done"


def _visible_task_keys(ctx, quests):
    keys = set()
    for quest_row in quests:
        rows = ctx.conn.execute(
            "SELECT tid FROM quest_tasks WHERE quest = ? AND state IN ('active', 'blocked')",
            (quest_row["slug"],),
        ).fetchall()
        keys.update((quest_row["slug"], row["tid"]) for row in rows)
    return keys


def _leader_session_name(conn, party_name):
    leader = conn.execute(
        "SELECT session_name FROM leaders WHERE party = ? ORDER BY generation DESC LIMIT 1",
        (party_name,),
    ).fetchone()
    if leader is None:
        return None
    return leader["session_name"]


def _leader_label(ctx, party_row):
    session_name = _leader_session_name(ctx.conn, party_row["name"]) or "no leader"
    role = raid_commands.raid_role_label(
        raid_commands.member_raids(ctx.conn, ctx.now, party_row["name"])
    )
    return "{} (gen {}, {}, {})".format(
        session_name, party_row["generation"], party_row["state"], role
    )


def _party_pr_rows(conn, party_name):
    return conn.execute(
        pr_asks.PRS_WITH_ASK_SQL + " WHERE party = ? ORDER BY repo ASC, number ASC", (party_name,)
    ).fetchall()


def _prs_by_task(pr_rows):
    result = {}
    for pr_row in pr_rows:
        result.setdefault((pr_row["task_quest"], pr_row["task_tid"]), []).append(pr_row)
    return result


def _active_quests(conn, party_name):
    return conn.execute(
        "SELECT * FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party_name,)
    ).fetchall()


def _orphan_pr_rows(ctx, quests, pr_rows):
    visible_keys = _visible_task_keys(ctx, quests)
    return [
        pr_row
        for pr_row in pr_rows
        if (pr_row["task_quest"], pr_row["task_tid"]) not in visible_keys
        and not _finished_with_task(ctx, pr_row)
    ]


def _party_claims(ctx, party_name):
    return [row for row in claim_commands.list_claims(ctx.conn, ctx.now) if row["party"] == party_name]


def _ctx_model(ctx, party_row, project_config):
    return ctx_pressure.for_party(ctx, party_row, config.load_global(paths.global_config_path()), project_config)


def _ctx_text(pressure):
    text = "  context: {}% (handoff at {}%".format(pressure["pct"], pressure["threshold"])
    if pressure["source"] != "configured":
        text += ", {}".format(pressure["source"])
    text += ")"
    if pressure["high"]:
        return text + " → run guild handoff"
    return text


def _resume_command(ctx, party_row):
    if party_row["state"] != "awaiting-leader":
        return None
    leader = ctx.conn.execute(
        "SELECT cwd, permission_mode FROM leaders WHERE party = ? AND generation = ?",
        (party_row["name"], party_row["generation"]),
    ).fetchone()
    command = resume.fresh_command(
        party_row["name"],
        party_row["generation"] + 1,
        None,
        None if leader is None else leader["permission_mode"],
        resume.RESUME_PROMPT,
    )
    if leader is None or leader["cwd"] is None:
        return command
    return "cd {} && {}".format(shlex.quote(leader["cwd"]), command)


def _plural(count, word):
    return "{} {}{}".format(count, word, "" if count == 1 else "s")


def _remaining_line(painter, remaining):
    if remaining["all_done"]:
        return painter.paint("  remaining: all done", "green")
    text = "  remaining: {} ({} active, {} blocked, {} queued) in {}".format(
        _plural(remaining["pending"], "task"),
        remaining["active"],
        remaining["blocked"],
        remaining["queued"],
        _plural(len(remaining["quests"]), "quest"),
    )
    if remaining["extra_prs"]:
        text += " + {} outside quests".format(_plural(remaining["extra_prs"], "PR"))
    return painter.paint(text, "yellow")


def _party_caps(ctx, party_row, project_config):
    if project_config is None:
        return None
    status = next_commands.cap_status(ctx.conn, ctx.projects_dir, party_row["name"], party_row["project"])
    return {"open": status["party_open"], "cap": status["party_cap"], "wait": status["party_wait"]}


def _party_cap_lines(painter, caps):
    lines = []
    if caps is None:
        return lines
    if caps["cap"] is not None:
        lines.append(painter.paint("  open PRs: {}/{}".format(caps["open"], caps["cap"]), "dim"))
    if caps["wait"] is not None:
        lines.append(painter.paint("  {}".format(caps["wait"]), "yellow"))
    return lines


def _project_models(ctx, party_rows, projects_by_name):
    models = []
    seen = set()
    for party_row in party_rows:
        project = party_row["project"]
        if project is None or project in seen or project not in projects_by_name:
            continue
        seen.add(project)
        caps = next_commands.cap_status(ctx.conn, ctx.projects_dir, party_row["name"], project)
        models.append(project_status.project_model(ctx, project, caps))
    return sorted(models, key=lambda model: model["name"])


def _project_lines(ctx, painter, party_rows, projects_by_name):
    lines = []
    for model in _project_models(ctx, party_rows, projects_by_name):
        lines.append("{} {}".format(painter.paint("━━", "cyan"), painter.paint("project " + model["name"], "bold")))
        lines.extend(project_status.project_lines(model))
        lines.append("")
    return lines


def _party_section(ctx, painter, party_row, project_config):
    lines = [
        "{} {}  {}".format(
            painter.paint("━━", "cyan"),
            painter.paint(party_row["name"], "bold"),
            painter.paint(_leader_label(ctx, party_row), "dim"),
        )
    ]
    status = party_status.derive(ctx, party_row)
    lines.append(
        painter.paint("  status: {}".format(party_status.label(ctx, status)), _STATUS_STYLES[status["status"]])
    )
    waits = party_waits.for_party(ctx, party_row)
    if waits:
        lines.append(painter.paint("  waits on: {}".format("; ".join(wait["label"] for wait in waits)), "yellow"))
    lines.append(_remaining_line(painter, party_progress.remaining(ctx.conn, party_row["name"])))
    lines.extend(_party_cap_lines(painter, _party_caps(ctx, party_row, project_config)))
    pressure = _ctx_model(ctx, party_row, project_config)
    if pressure is not None:
        lines.append(painter.paint(_ctx_text(pressure), "red" if pressure["high"] else "dim"))
    resume_command = _resume_command(ctx, party_row)
    if resume_command is not None:
        lines.append(painter.paint("  resume: {}".format(resume_command), "cyan"))
    next_ref = merge_queue_commands.next_to_merge(ctx.conn, {party_row["name"]})
    for text in merge_queue_commands.main_board_texts(ctx.conn, {party_row["name"]}):
        lines.append(painter.paint("  {}".format(text), "red"))
    if next_ref is not None:
        lines.append(painter.paint("  next to merge: {}".format(next_ref), "green"))
    pr_rows = _party_pr_rows(ctx.conn, party_row["name"])
    prs_by_task = _prs_by_task(pr_rows)
    quests = _active_quests(ctx.conn, party_row["name"])
    for quest_row in quests:
        lines.extend(_quest_lines(ctx, painter, quest_row, prs_by_task))
    orphan_prs = _orphan_pr_rows(ctx, quests, pr_rows)
    if orphan_prs:
        lines.append(painter.paint("  PRs outside active tasks", "dim"))
        for pr_row in orphan_prs:
            lines.extend(_pr_lines(ctx, painter, pr_row, "    "))
    claims = _party_claims(ctx, party_row["name"])
    if claims:
        claim_text = ", ".join(
            "{} ({})".format(row["area"], timeutil.time_left_label(ctx.now, row["expires_at"])) for row in claims
        )
        lines.append(painter.paint("  claims: {}".format(claim_text), "dim"))
    raids = raid_commands.member_raids(ctx.conn, ctx.now, party_row["name"])
    if raids:
        raid_text = ", ".join(
            "{} ({}{})".format(
                row["raid"],
                "PAUSED, " if raid_commands.is_paused(ctx.conn, row["raid"]) else "",
                raid_commands.membership_label(ctx.now, row),
            )
            for row in raids
        )
        lines.append(painter.paint("  raids: {}".format(raid_text), "dim"))
    lines.append("")
    return lines


def _party_rows_for_names(conn, party_names):
    if not party_names:
        return []
    placeholders = ", ".join("?" for _ in party_names)
    query = "SELECT * FROM parties WHERE name IN ({}) ORDER BY name ASC".format(placeholders)
    return conn.execute(query, tuple(party_names)).fetchall()


def _raid_next_to_merge_lines(ctx, painter, party_names):
    next_ref = merge_queue_commands.next_to_merge(ctx.conn, party_names)
    lines = [
        painter.paint(text, "red")
        for text in merge_queue_commands.main_board_texts(ctx.conn, party_names)
    ]
    if next_ref is not None:
        lines.append(painter.paint("next to merge: {}".format(next_ref), "green"))
    if not lines:
        return []
    return lines + [""]


def _ready_item_lines(painter, item):
    suffix = " · review first" if item["review_first"] else ""
    lines = painter.wrap("{} {} · {}{}".format(item["ref"], item["title"], item["party"], suffix), "  ")
    for note in item["notes"]:
        lines.extend(painter.wrap("note: {}".format(note), "    "))
    return lines


def _ready_for_you_lines(ctx, painter, party_filter, raid_filter):
    party_rows = ctx.conn.execute("SELECT name FROM parties WHERE state != 'closed'").fetchall()
    scopes = merge_queue_commands.board_scopes(ctx.conn, ctx.now, {row["name"] for row in party_rows})
    items = merge_queue_commands.ready_for_you(ctx.conn, ctx.projects_dir, scopes)
    if party_filter is not None:
        items = [item for item in items if item["party"] == party_filter]
    if raid_filter is not None:
        items = [item for item in items if "raid:{}".format(raid_filter) in item["scopes"]]
    if not items:
        return [painter.paint("READY FOR YOU · nothing", "green"), ""]
    lines = [painter.paint("READY FOR YOU · {}".format(len(items)), "bold")]
    for item in items:
        lines.extend(_ready_item_lines(painter, item))
    lines.append("")
    return lines


def render_board(ctx, party_filter, raid_filter, color, width):
    painter = _Painter(color, width)
    if raid_filter is not None:
        members = raid_commands.require_active_raid(ctx.conn, ctx.now, raid_filter)
        party_names = {row["party"] for row in members}
        party_rows = _party_rows_for_names(ctx.conn, party_names)
        notice_rows = _raid_scoped_notices(ctx, raid_filter)
    elif party_filter is not None:
        party_names = {party_filter}
        party_rows = ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (party_filter,)).fetchall()
        notice_rows = _party_scoped_notices(ctx, party_filter)
    else:
        party_names = None
        party_rows = ctx.conn.execute(
            "SELECT * FROM parties WHERE state != 'closed' ORDER BY name ASC"
        ).fetchall()
        notice_rows = _party_scoped_notices(ctx, None)
    lines = []
    if raid_filter is not None and raid_commands.is_paused(ctx.conn, raid_filter):
        lines.extend([painter.paint("raid {} PAUSED".format(raid_filter), "red"), ""])
    if raid_filter is not None:
        lines.extend(_raid_next_to_merge_lines(ctx, painter, party_names))
    lines.extend(render_asks(ctx, party_names, color, width, False))
    lines.extend(_ready_for_you_lines(ctx, painter, party_filter, raid_filter))
    lines.extend(_notices_section(ctx, painter, notice_rows))
    projects_by_name = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    lines.extend(_project_lines(ctx, painter, party_rows, projects_by_name))
    for party_row in party_rows:
        lines.extend(
            _party_section(ctx, painter, party_row, projects_by_name.get(party_row["project"]))
        )
    return lines


def _optional_text(value):
    if not value:
        return None
    return sanitize.strip_control_sequences(value)


def _pr_model(ctx, pr_row, project_config):
    card = _optional_text(pr_row["card"])
    return {
        "repo": pr_row["repo"],
        "number": pr_row["number"],
        "lifecycle": pr_row["lifecycle"],
        "needs_ask_answer": pr_asks.needs_answer(pr_row),
        "ask_id": pr_row["open_ask_id"],
        "needs_human_pr_review": bool(pr_row["needs_human_pr_review"]),
        "fixes_main": bool(pr_row["fixes_main"]),
        "fixes_flaky": bool(pr_row["fixes_flaky"]),
        "blocked_external": _optional_text(pr_row["blocked_external"]),
        "party": pr_row["party"],
        "checks_failing": pr_row["checks_failing"] or 0,
        "checks_passing": pr_row["checks_passing"] or 0,
        "checks_pending": pr_row["checks_pending"] or 0,
        "what": sanitize.strip_control_sequences(pr_row["what"]),
        "waits": _optional_text(_visible_waits(pr_row)),
        "branch": _optional_text(pr_row["branch"]),
        "base_branch": _optional_text(pr_row["base_branch"]),
        "review_reasons": merge_queue.review_reasons(
            pr_row["mergeable"], pr_row["review_decision"], pr_row["unresolved_threads"], pr_row["merge_state"]
        ),
        "card": card,
        "card_url": links.card_url(project_config, card),
        "url": links.pr_url(pr_row["repo"], pr_row["number"]),
    }


def _task_card_key(conn, project, epic, tid):
    if project is None or epic is None:
        return None
    row = conn.execute(
        "SELECT jira_key FROM tasks WHERE project = ? AND epic = ? AND tid = ?",
        (project, epic, tid),
    ).fetchone()
    if row is None:
        return None
    return row["jira_key"]


def _ask_model(conn, row):
    ref_list = json.loads(row["refs"])
    return {
        "id": row["id"],
        "party": row["party"],
        "question": sanitize.strip_control_sequences(row["question"]),
        "context": sanitize.strip_control_sequences(row["context"]),
        "options": json.loads(row["options"]),
        "refs": ref_list,
        "blocked": _blocked_ref_count(conn, ref_list),
        "total_refs": len(ref_list),
        "created_at": row["created_at"],
        "state": row["state"],
        "answer": _optional_text(row["answer"]),
        "answered_at": row["answered_at"],
    }


def _notice_model(ctx, row):
    return {
        "id": row["id"],
        "party": row["party"],
        "author": identity.actor_label(row["party"], bool(row["unbound"])),
        "scope": row["scope"],
        "text": sanitize.strip_control_sequences(row["text"]),
        "issued_at": row["created_at"],
        "issued": timeutil.issued_label(row["created_at"]),
        "expires_at": row["expires_at"],
        "time_left": timeutil.time_left_label(ctx.now, row["expires_at"]),
        "seen": not notice_commands.is_new(row),
        "flagged": _notice_flagged(row),
    }


def _idea_model(ctx, row):
    return {
        "id": row["id"],
        "title": sanitize.strip_control_sequences(row["title"]),
        "description": sanitize.strip_control_sequences(row["description"]),
        "requester": row["requester"],
        "deadline": row["deadline"],
        "project": row["project"],
        "created_at": row["created_at"],
        "overdue": idea_commands.is_overdue(ctx.now, row["deadline"]),
    }


def _memory_item_model(item):
    return {
        "id": item["id"],
        "party": item["party"],
        "text": item["text"],
        "flagged": memory_commands.flagged(item["text"]),
    }


def _task_model(ctx, project, epic, task_row, task_prs, project_config):
    key = _task_card_key(ctx.conn, project, epic, task_row["tid"])
    return {
        "tid": task_row["tid"],
        "title": sanitize.strip_control_sequences(task_row["title"]),
        "state": task_row["state"],
        "summary": _optional_text(task_row["summary"]),
        "blocked_reason": _optional_text(task_row["blocked_reason"]),
        "card_url": links.card_url(project_config, key),
        "prs": [_pr_model(ctx, pr_row, project_config) for pr_row in task_prs],
    }


def _move_targets(conn, quest_row):
    rows = conn.execute(
        "SELECT slug FROM quests WHERE state = 'active' AND project = ? AND slug != ?"
        " AND epic IS ? ORDER BY slug ASC",
        (quest_row["project"], quest_row["slug"], quest_row["epic"]),
    ).fetchall()
    return [row["slug"] for row in rows]


def _quest_model(ctx, project, quest_row, prs_by_task, project_config):
    task_rows = _open_task_rows(ctx.conn, quest_row["slug"])
    tasks = [
        _task_model(
            ctx,
            project,
            quest_row["epic"],
            task_row,
            prs_by_task.get((quest_row["slug"], task_row["tid"]), []),
            project_config,
        )
        for task_row in task_rows
    ]
    return {
        "slug": quest_row["slug"],
        "title": sanitize.strip_control_sequences(quest_row["title"]),
        "move_targets": _move_targets(ctx.conn, quest_row),
        "close_blockers": _close_blockers(ctx, quest_row),
        "tasks": tasks,
    }


def _status_model(ctx, party_row):
    status = party_status.derive(ctx, party_row)
    detail = status["detail"]
    return {
        "name": status["status"],
        "since": status["since"],
        "detail": _optional_text(detail),
        "label": party_status.label(ctx, status),
    }


def _blocked_model(ctx, row):
    status = {"status": "waiting-permission", "since": row["since"], "detail": row["detail"]}
    return {
        "party": row["party"],
        "wait": "permission",
        "since": row["since"],
        "detail": _optional_text(row["detail"]),
        "label": party_status.label(ctx, status),
    }


def _party_drift_model(ctx, party_row):
    findings = drift_commands.party_findings(ctx.conn, party_row["project"], party_row["name"])
    return {
        "findings": findings[:brief_commands.DRIFT_BRIEF_CAP],
        "more": max(0, len(findings) - brief_commands.DRIFT_BRIEF_CAP),
    }


def _party_model(ctx, party_row, project_config):
    pr_rows = _party_pr_rows(ctx.conn, party_row["name"])
    prs_by_task = _prs_by_task(pr_rows)
    quests = _active_quests(ctx.conn, party_row["name"])
    quest_models = [
        _quest_model(ctx, party_row["project"], quest_row, prs_by_task, project_config)
        for quest_row in quests
    ]
    orphan_prs = _orphan_pr_rows(ctx, quests, pr_rows)
    claims = _party_claims(ctx, party_row["name"])
    raids = raid_commands.member_raids(ctx.conn, ctx.now, party_row["name"])
    return {
        "name": party_row["name"],
        "state": party_row["state"],
        "generation": party_row["generation"],
        "status": _status_model(ctx, party_row),
        "remaining": party_progress.remaining(ctx.conn, party_row["name"]),
        "waits": party_waits.for_party(ctx, party_row),
        "drift": _party_drift_model(ctx, party_row),
        "ctx": _ctx_model(ctx, party_row, project_config),
        "caps": _party_caps(ctx, party_row, project_config),
        "resume_command": _resume_command(ctx, party_row),
        "leader_session_name": _leader_session_name(ctx.conn, party_row["name"]),
        "has_live_leader": party_status.has_live_leader(ctx, party_row),
        "quests": quest_models,
        "prs": [_pr_model(ctx, pr_row, project_config) for pr_row in orphan_prs],
        "raids": [
            {
                "raid": row["raid"],
                "expires_at": row["expires_at"],
                "paused": raid_commands.is_paused(ctx.conn, row["raid"]),
            }
            for row in raids
        ],
        "claims": [{"area": row["area"], "expires_at": row["expires_at"]} for row in claims],
    }


def _raid_model(conn, raid_name, members):
    return {
        "name": raid_name,
        "members": [row["party"] for row in members],
        "paused": raid_commands.is_paused(conn, raid_name),
    }


def _raid_models(conn, now):
    grouped = raid_commands.active_raids_grouped(conn, now)
    return [_raid_model(conn, raid_name, grouped[raid_name]) for raid_name in sorted(grouped)]


def board_model(ctx):
    party_rows = ctx.conn.execute(
        "SELECT * FROM parties WHERE state != 'closed' ORDER BY name ASC"
    ).fetchall()
    projects_by_name = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    ask_rows = _sorted_open_asks(ctx.conn, None)
    notice_rows = notice_commands.active_notices(ctx.conn, ctx.now)
    project_names = sorted({row["project"] for row in party_rows if row["project"] is not None})
    live_party_names = {row["name"] for row in party_rows}
    scopes = merge_queue_commands.board_scopes(ctx.conn, ctx.now, live_party_names)
    return {
        "generated_at": timeutil.to_iso(ctx.now),
        "asks": [_ask_model(ctx.conn, row) for row in ask_rows],
        "notices": [_notice_model(ctx, row) for row in notice_rows],
        "new_notice_count": notice_commands.count_new(notice_rows),
        "ideas": [_idea_model(ctx, row) for row in idea_commands.sorted_rows(ctx, None)],
        "memory": [
            _memory_item_model(item)
            for item in memory_commands.all_items(None)
            if item["party"] in live_party_names
        ],
        "parties": [
            _party_model(ctx, party_row, projects_by_name.get(party_row["project"]))
            for party_row in party_rows
        ],
        "blocked": [_blocked_model(ctx, row) for row in session_status.blocked_rows(ctx.conn, None)],
        "drift": [drift_commands.board_findings(ctx, project_name) for project_name in project_names],
        "raids": _raid_models(ctx.conn, ctx.now),
        "merge_queues": merge_queue_commands.board_models(ctx.projects_dir, ctx.now, scopes),
        "ready_for_you": merge_queue_commands.ready_for_you(ctx.conn, ctx.projects_dir, scopes),
        "projects": _project_models(ctx, party_rows, projects_by_name),
    }

