import json
import textwrap

from guild import sanitize, timeutil
from guild.commands import claim as claim_commands
from guild.commands import notice as notice_commands

_STYLES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
    "magenta": "35",
}

_LIFECYCLE_STYLES = {
    "needs-human": "red",
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


def _time_left(now, expires_at_text):
    remaining = timeutil.from_iso(expires_at_text) - now
    hours = int(remaining.total_seconds() // 3600)
    if hours >= 1:
        return "{}h left".format(hours)
    return "{}m left".format(int(remaining.total_seconds() // 60))


def _checks_parts(pr_row):
    failing = pr_row["checks_failing"] or 0
    passing = pr_row["checks_passing"] or 0
    if failing == 0 and passing == 0:
        return None
    return failing, passing


def _checks_plain(pr_row):
    parts = _checks_parts(pr_row)
    if parts is None:
        return "no checks"
    return "✗{} ✓{}".format(parts[0], parts[1])


def _checks_painted(painter, pr_row):
    parts = _checks_parts(pr_row)
    if parts is None:
        return painter.paint("no checks", "dim")
    failing_style = "red" if parts[0] > 0 else "dim"
    return "{} {}".format(
        painter.paint("✗{}".format(parts[0]), failing_style),
        painter.paint("✓{}".format(parts[1]), "green"),
    )


def _pr_lines(painter, pr_row, indent):
    lifecycle = pr_row["lifecycle"]
    status_plain = "{}  {}".format(lifecycle, _checks_plain(pr_row))
    status_painted = "{}  {}".format(
        painter.paint(lifecycle, _LIFECYCLE_STYLES[lifecycle]), _checks_painted(painter, pr_row)
    )
    plain_head = "● {}#{}  {}  {}".format(
        pr_row["repo"].split("/")[-1],
        pr_row["number"],
        status_plain,
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
    if not pr_row["waits"]:
        return head_lines
    return head_lines + painter.wrap("waits: {}".format(pr_row["waits"]), indent + "  ")


def _ask_detail_lines(painter, row):
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
    lines.append(painter.paint("     refs: {}".format(", ".join(json.loads(row["refs"]))), "dim"))
    lines.append(painter.paint('     → guild answer {} "..."'.format(row["id"]), "dim"))
    lines.append("")
    return lines


def _ask_summary_lines(painter, row):
    option_list = json.loads(row["options"])
    options_text = "  [{}]".format(" | ".join(option_list)) if option_list else ""
    wrapped = painter.wrap("{} · {}{}".format(row["party"], row["question"], options_text), "      ")
    first = "  {} {}".format(painter.paint("#{}".format(row["id"]), "red"), wrapped[0].strip())
    return [first] + wrapped[1:]


def _ask_sort_key(row):
    return (-len(json.loads(row["refs"])), row["created_at"], row["id"])


def render_asks(ctx, party_filter, color, width, detailed):
    painter = _Painter(color, width)
    rows = ctx.conn.execute("SELECT * FROM asks WHERE state = 'open'").fetchall()
    rows = sorted(rows, key=_ask_sort_key)
    if party_filter is not None:
        rows = [row for row in rows if row["party"] == party_filter]
    if not rows:
        return [painter.paint("NEEDS YOU · nothing", "green"), ""]
    label = "open ask" if len(rows) == 1 else "open asks"
    lines = [painter.paint("NEEDS YOU · {} {}".format(len(rows), label), "bold")]
    if detailed:
        for row in rows:
            lines.extend(_ask_detail_lines(painter, row))
        return lines
    for row in rows:
        lines.extend(_ask_summary_lines(painter, row))
    lines.append(painter.paint('  → guild asks (context) · guild answer <id> "..."', "dim"))
    lines.append("")
    return lines


def _notices_section(ctx, painter, party_filter):
    rows = notice_commands.active_notices(ctx.conn, ctx.now)
    if party_filter is not None:
        rows = [row for row in rows if row["party"] == party_filter]
    if not rows:
        return []
    lines = [painter.paint("NOTICES · {} active".format(len(rows)), "bold")]
    for row in rows:
        lines.append(
            "  {} {} · {}".format(
                painter.paint("#{}".format(row["id"]), "yellow"),
                painter.paint(row["party"] or "human", "cyan"),
                painter.paint("{} · {}".format(row["scope"], _time_left(ctx.now, row["expires_at"])), "dim"),
            )
        )
        lines.extend(painter.wrap(row["text"], "     "))
    lines.append("")
    return lines


def _task_lines(painter, task_row, task_prs):
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
        lines.extend(_pr_lines(painter, pr_row, "        "))
    return lines


def _quest_lines(ctx, painter, quest_row, prs_by_task):
    title = sanitize.strip_control_sequences(quest_row["title"])
    lines = ["  {} — {}".format(painter.paint(quest_row["slug"], "bold"), title)]
    task_rows = ctx.conn.execute(
        "SELECT * FROM quest_tasks WHERE quest = ? AND state != 'done' ORDER BY tid ASC",
        (quest_row["slug"],),
    ).fetchall()
    queued = []
    for task_row in task_rows:
        if task_row["state"] == "queued":
            queued.append(task_row["tid"])
            continue
        task_prs = prs_by_task.get((quest_row["slug"], task_row["tid"]), [])
        lines.extend(_task_lines(painter, task_row, task_prs))
    if queued:
        lines.append(painter.paint("    ○ queued: {}".format(", ".join(queued)), "dim"))
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


def _leader_label(ctx, party_row):
    leader = ctx.conn.execute(
        "SELECT session_name FROM leaders WHERE party = ? ORDER BY generation DESC LIMIT 1",
        (party_row["name"],),
    ).fetchone()
    session_name = leader["session_name"] if leader is not None and leader["session_name"] else "no leader"
    return "{} (gen {}, {})".format(session_name, party_row["generation"], party_row["state"])


def _party_section(ctx, painter, party_row):
    lines = [
        "{} {}  {}".format(
            painter.paint("━━", "cyan"),
            painter.paint(party_row["name"], "bold"),
            painter.paint(_leader_label(ctx, party_row), "dim"),
        )
    ]
    pr_rows = ctx.conn.execute(
        "SELECT * FROM prs WHERE party = ? ORDER BY repo ASC, number ASC", (party_row["name"],)
    ).fetchall()
    prs_by_task = {}
    for pr_row in pr_rows:
        prs_by_task.setdefault((pr_row["task_quest"], pr_row["task_tid"]), []).append(pr_row)
    quests = ctx.conn.execute(
        "SELECT * FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party_row["name"],)
    ).fetchall()
    for quest_row in quests:
        lines.extend(_quest_lines(ctx, painter, quest_row, prs_by_task))
    visible_keys = _visible_task_keys(ctx, quests)
    orphan_prs = [
        pr_row
        for pr_row in pr_rows
        if (pr_row["task_quest"], pr_row["task_tid"]) not in visible_keys
        and not _finished_with_task(ctx, pr_row)
    ]
    if orphan_prs:
        lines.append(painter.paint("  PRs outside active tasks", "dim"))
        for pr_row in orphan_prs:
            lines.extend(_pr_lines(painter, pr_row, "    "))
    claims = [row for row in claim_commands.list_claims(ctx.conn, ctx.now) if row["party"] == party_row["name"]]
    if claims:
        claim_text = ", ".join(
            "{} ({})".format(row["area"], _time_left(ctx.now, row["expires_at"])) for row in claims
        )
        lines.append(painter.paint("  claims: {}".format(claim_text), "dim"))
    lines.append("")
    return lines


def render_board(ctx, party_filter, color, width):
    painter = _Painter(color, width)
    if party_filter is not None:
        party_rows = ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (party_filter,)).fetchall()
    else:
        party_rows = ctx.conn.execute(
            "SELECT * FROM parties WHERE state != 'closed' ORDER BY name ASC"
        ).fetchall()
    lines = render_asks(ctx, party_filter, color, width, False) + _notices_section(ctx, painter, party_filter)
    for party_row in party_rows:
        lines.extend(_party_section(ctx, painter, party_row))
    return lines
