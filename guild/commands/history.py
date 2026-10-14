import json
import statistics
from datetime import timedelta

from guild import config, party_progress, timeutil

_WEEK = timedelta(days=7)

_KINDS = (
    "quest.added",
    "quest.done",
    "quest.marked_incomplete",
    "task.added",
    "task.started",
    "task.done",
    "task.blocked",
    "pr.tracked",
    "pr.set",
    "pr.synced",
    "ask.created",
    "ask.answered",
    "party.handed_off",
    "party.closed",
    "raid.joined",
    "raid.left",
    "raid.paused",
    "lifecycle.ran",
)
_LIFECYCLE_FAILURE_STATUSES = ("failed", "timeout", "error")
_SNAPSHOT_KEYS = (
    "started_at",
    "done_at",
    "party",
    "project",
    "epic",
    "title",
    "tasks_done",
    "tasks_blocked_events",
    "sdd_tids",
    "epic_progress",
    "jira_cards_done",
    "prs_merged",
    "handoffs",
    "sessions",
    "asks_raised",
    "asks_answered",
    "median_answer_seconds",
    "drift",
)


class _Scope:
    def __init__(self, party, project, raid_parties):
        self._party = party
        self._project = project
        self._raid_parties = raid_parties

    def admits(self, party, project):
        if self._party is not None and party != self._party:
            return False
        if self._project is not None and project != self._project:
            return False
        if self._raid_parties is not None and party not in self._raid_parties:
            return False
        return True

    def admits_project(self, project):
        return self._project is None or project == self._project


def _load_events(conn):
    marks = ", ".join("?" for _ in _KINDS)
    rows = conn.execute(
        "SELECT seq, ts, party, project, kind, payload FROM events"
        " WHERE kind IN ({}) ORDER BY seq ASC".format(marks),
        _KINDS,
    ).fetchall()
    by_kind = {kind: [] for kind in _KINDS}
    for row in rows:
        by_kind[row["kind"]].append(
            {
                "seq": row["seq"],
                "ts": row["ts"],
                "party": row["party"],
                "project": row["project"],
                "payload": json.loads(row["payload"]),
            }
        )
    return by_kind


def _raid_parties(by_kind, raid):
    if raid is None:
        return None
    return {
        event["payload"]["party"] for event in by_kind["raid.joined"] if event["payload"]["raid"] == raid
    }


def _ref(repo, number):
    return "{}#{}".format(repo, number)


def _seconds_between(start_iso, end_iso):
    if start_iso is None or end_iso is None:
        return None
    return int((timeutil.from_iso(end_iso) - timeutil.from_iso(start_iso)).total_seconds())


def _merged_pr_records(by_kind):
    tracked = {}
    for event in by_kind["pr.tracked"]:
        payload = event["payload"]
        tracked[(payload["repo"], payload["number"])] = {
            "ref": _ref(payload["repo"], payload["number"]),
            "party": event["party"],
            "project": event["project"],
            "quest": payload["task_quest"],
            "merged_at": None,
        }
    lifecycle_events = by_kind["pr.tracked"] + by_kind["pr.set"] + by_kind["pr.synced"]
    for event in sorted(lifecycle_events, key=lambda item: timeutil.from_iso(item["ts"])):
        payload = event["payload"]
        record = tracked.get((payload["repo"], payload["number"]))
        if record is None or record["merged_at"] is not None or payload["lifecycle"] != "merged":
            continue
        record["merged_at"] = event["ts"]
    merged = [record for record in tracked.values() if record["merged_at"] is not None]
    return sorted(merged, key=lambda record: record["ref"])


def _in_window(ts, started_at, ended_at):
    moment = timeutil.from_iso(ts)
    if started_at is not None and moment < timeutil.from_iso(started_at):
        return False
    return moment <= timeutil.from_iso(ended_at)


def _newest_created_first(entries, name_key):
    dated = sorted(
        (entry for entry in entries if entry["started_at"] is not None),
        key=lambda entry: entry[name_key],
    )
    dated.sort(key=lambda entry: timeutil.from_iso(entry["started_at"]), reverse=True)
    undated = sorted(
        (entry for entry in entries if entry["started_at"] is None),
        key=lambda entry: entry[name_key],
    )
    return dated + undated


def _snapshot_quest(slug, snapshot):
    quest = {key: snapshot[key] for key in _SNAPSHOT_KEYS}
    quest["slug"] = slug
    quest["snapshot"] = True
    quest["duration_seconds"] = _seconds_between(snapshot["started_at"], snapshot["done_at"])
    return quest


def _distinct_done_tids(by_kind, slug):
    return sorted(
        {event["payload"]["tid"] for event in by_kind["task.done"] if event["payload"]["quest"] == slug}
    )


def _legacy_quest(by_kind, merged_prs, added_by_slug, done_event):
    slug = done_event["payload"]["slug"]
    added = added_by_slug.get(slug)
    started_at = None if added is None else added["ts"]
    party = done_event["party"] if added is None else added["payload"]["party"]
    project = done_event["project"] if added is None else added["payload"]["project"]
    done_at = done_event["ts"]
    tids = _distinct_done_tids(by_kind, slug)
    blocked = sum(1 for event in by_kind["task.blocked"] if event["payload"]["quest"] == slug)
    handoffs = sum(
        1
        for event in by_kind["party.handed_off"]
        if event["party"] == party and _in_window(event["ts"], started_at, done_at)
    )
    return {
        "slug": slug,
        "snapshot": False,
        "started_at": started_at,
        "done_at": done_at,
        "duration_seconds": _seconds_between(started_at, done_at),
        "party": party,
        "project": project,
        "epic": None if added is None else added["payload"]["epic"],
        "title": slug if added is None else added["payload"]["title"],
        "tasks_done": len(tids),
        "tasks_blocked_events": blocked,
        "sdd_tids": tids,
        "epic_progress": None,
        "jira_cards_done": [],
        "prs_merged": [record["ref"] for record in merged_prs if record["quest"] == slug],
        "handoffs": handoffs,
        "sessions": None,
        "asks_raised": None,
        "asks_answered": None,
        "median_answer_seconds": None,
        "drift": [],
    }


def _all_quests(by_kind, merged_prs):
    added_by_slug = {event["payload"]["slug"]: event for event in by_kind["quest.added"]}
    quests = {}
    for event in by_kind["quest.done"]:
        slug = event["payload"]["slug"]
        if slug in quests:
            continue
        snapshot = event["payload"].get("achievement")
        if snapshot is None:
            quests[slug] = _legacy_quest(by_kind, merged_prs, added_by_slug, event)
            continue
        quests[slug] = _snapshot_quest(slug, snapshot)
    return _newest_created_first(list(quests.values()), "slug")


def _percent(done, total):
    if total == 0:
        return 0
    return done * 100 // total


def _stale_hours(projects_dir, project):
    if project is None:
        return None
    config_file = projects_dir / "{}.json".format(project)
    if not config_file.is_file():
        return None
    next_config = config.load_project_file(config_file).get("next")
    if next_config is None:
        return None
    return next_config.get("stale_hours")


def _latest(timestamps):
    if not timestamps:
        return None
    return max(timestamps, key=timeutil.from_iso)


def _quest_pr_keys(by_kind, slug):
    return {
        (event["payload"]["repo"], event["payload"]["number"])
        for event in by_kind["pr.tracked"]
        if event["payload"]["task_quest"] == slug
    }


def _quest_activity_timestamps(by_kind, slug):
    timestamps = [
        event["ts"]
        for kind in ("task.added", "task.started", "task.done", "task.blocked")
        for event in by_kind[kind]
        if event["payload"]["quest"] == slug
    ]
    pr_keys = _quest_pr_keys(by_kind, slug)
    timestamps.extend(
        event["ts"]
        for kind in ("pr.tracked", "pr.set", "pr.synced")
        for event in by_kind[kind]
        if (event["payload"]["repo"], event["payload"]["number"]) in pr_keys
    )
    return timestamps


def _party_activity_timestamps(by_kind, party):
    return [event["ts"] for events in by_kind.values() for event in events if event["party"] == party]


def _last_activity_at(by_kind, slug, party, started_at):
    quest_latest = _latest(_quest_activity_timestamps(by_kind, slug))
    if quest_latest is not None:
        return quest_latest
    party_latest = _latest(_party_activity_timestamps(by_kind, party))
    if party_latest is not None:
        return party_latest
    return started_at


def _active_quest_entry(conn, by_kind, now, projects_dir, started_at, row):
    tasks = party_progress.task_counts(conn, row["slug"])
    return {
        "slug": row["slug"],
        "party": row["party"],
        "project": row["project"],
        "epic": row["epic"],
        "title": row["title"],
        "started_at": started_at,
        "age_seconds": _seconds_between(started_at, timeutil.to_iso(now)),
        "last_activity_at": _last_activity_at(by_kind, row["slug"], row["party"], started_at),
        "stale_hours": _stale_hours(projects_dir, row["project"]),
        "tasks": tasks,
        "percent_done": _percent(tasks["done"], tasks["total"]),
    }


def _active_quests(conn, by_kind, now, projects_dir, scope):
    started_by_slug = {}
    for event in by_kind["quest.added"]:
        started_by_slug.setdefault(event["payload"]["slug"], event["ts"])
    rows = conn.execute(
        "SELECT slug, party, project, epic, title FROM quests WHERE state = 'active'"
    ).fetchall()
    entries = [
        _active_quest_entry(conn, by_kind, now, projects_dir, started_by_slug.get(row["slug"]), row)
        for row in rows
        if scope.admits(row["party"], row["project"])
    ]
    return _newest_created_first(entries, "slug")


def _first_marks(by_kind):
    marks = {}
    for event in by_kind["quest.marked_incomplete"]:
        marks.setdefault(event["payload"]["slug"], event)
    return marks


def _quest_tids(by_kind, slug):
    tids = set()
    for event in by_kind["quest.added"]:
        if event["payload"]["slug"] == slug:
            tids.update(task["tid"] for task in event["payload"]["tasks"])
    for event in by_kind["task.added"]:
        if event["payload"]["quest"] == slug:
            tids.add(event["payload"]["tid"])
    return tids


def _done_tids_before(by_kind, slug, seq):
    return {
        event["payload"]["tid"]
        for event in by_kind["task.done"]
        if event["payload"]["quest"] == slug and event["seq"] < seq
    }


def _incomplete_entry(by_kind, quests_by_slug, added_by_slug, mark):
    slug = mark["payload"]["slug"]
    quest = quests_by_slug.get(slug)
    added = added_by_slug.get(slug)
    all_tids = _quest_tids(by_kind, slug)
    not_done = all_tids - _done_tids_before(by_kind, slug, mark["seq"])
    if quest is not None:
        base = {key: quest[key] for key in ("party", "project", "title", "started_at", "done_at")}
    elif added is not None:
        base = {
            "party": added["payload"]["party"],
            "project": added["payload"]["project"],
            "title": added["payload"]["title"],
            "started_at": added["ts"],
            "done_at": None,
        }
    else:
        base = {
            "party": mark["party"],
            "project": mark["project"],
            "title": slug,
            "started_at": None,
            "done_at": None,
        }
    return dict(
        base,
        slug=slug,
        marked_at=mark["ts"],
        reason=mark["payload"]["reason"],
        tasks_not_done=len(not_done),
        tasks_total=len(all_tids),
    )


def _incomplete_quests(by_kind, scope, every_quest):
    quests_by_slug = {quest["slug"]: quest for quest in every_quest}
    added_by_slug = {}
    for event in by_kind["quest.added"]:
        added_by_slug.setdefault(event["payload"]["slug"], event)
    entries = [
        _incomplete_entry(by_kind, quests_by_slug, added_by_slug, mark)
        for mark in _first_marks(by_kind).values()
    ]
    admitted = [entry for entry in entries if scope.admits(entry["party"], entry["project"])]
    return _newest_created_first(admitted, "slug")


def _end_span(span, ts):
    ended_at = ts
    if span["expires_at"] is not None and timeutil.from_iso(span["expires_at"]) < timeutil.from_iso(ts):
        ended_at = span["expires_at"]
    span["ended_at"] = ended_at


def _open_spans(spans, party):
    return [span for span in spans if span["party"] == party and span["ended_at"] is None]


def _apply_join(spans, event):
    payload = event["payload"]
    open_spans = _open_spans(spans, payload["party"])
    if open_spans:
        open_spans[0]["expires_at"] = payload["expires_at"]
        return
    spans.append(
        {
            "party": payload["party"],
            "project": event["project"],
            "started_at": event["ts"],
            "expires_at": payload["expires_at"],
            "ended_at": None,
        }
    )


def _apply_end(spans, party, ts):
    for span in _open_spans(spans, party):
        _end_span(span, ts)


def _membership_spans(by_kind):
    membership_events = [("joined", event) for event in by_kind["raid.joined"]]
    membership_events += [("left", event) for event in by_kind["raid.left"]]
    membership_events += [("closed", event) for event in by_kind["party.closed"]]
    membership_events.sort(key=lambda item: item[1]["seq"])
    spans_by_raid = {}
    for action, event in membership_events:
        payload = event["payload"]
        if action == "closed":
            for spans in spans_by_raid.values():
                _apply_end(spans, payload["party"], event["ts"])
        elif action == "left":
            _apply_end(spans_by_raid.get(payload["raid"], []), payload["party"], event["ts"])
        else:
            _apply_join(spans_by_raid.setdefault(payload["raid"], []), event)
    return spans_by_raid


def _is_active(now, spans):
    return any(
        span["ended_at"] is None and not timeutil.is_expired(now, span["expires_at"]) for span in spans
    )


def _span_end(span):
    if span["ended_at"] is not None:
        return span["ended_at"]
    return span["expires_at"]


def _raid_parties_summary(spans):
    return sorted({span["party"] for span in spans})


def _raid_entry(by_kind, quests, merged_prs, name, spans):
    started_at = min((span["started_at"] for span in spans), key=timeutil.from_iso)
    ended_at = max((_span_end(span) for span in spans), key=timeutil.from_iso)
    parties = _raid_parties_summary(spans)
    member_names = set(parties)
    return {
        "name": name,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": _seconds_between(started_at, ended_at),
        "parties": parties,
        "quests": [
            {"slug": quest["slug"], "party": quest["party"], "title": quest["title"]}
            for quest in quests
            if quest["party"] in member_names and _in_window(quest["done_at"], started_at, ended_at)
        ],
        "prs_merged": [
            record["ref"]
            for record in merged_prs
            if record["party"] in member_names and _in_window(record["merged_at"], started_at, ended_at)
        ],
        "pauses": sum(1 for event in by_kind["raid.paused"] if event["payload"]["raid"] == name),
    }


def _finished_raids(by_kind, now, scope, raid, quests, merged_prs):
    raids = []
    for name, spans in _membership_spans(by_kind).items():
        if raid is not None and name != raid:
            continue
        if _is_active(now, spans):
            continue
        if not any(scope.admits(span["party"], span["project"]) for span in spans):
            continue
        raids.append(_raid_entry(by_kind, quests, merged_prs, name, spans))
    return _newest_created_first(raids, "name")


def _since_cutoff(ts, cutoff):
    if cutoff is None:
        return True
    return timeutil.from_iso(ts) >= cutoff


def _answer_seconds(by_kind, scope, cutoff):
    answered_at = {}
    for event in by_kind["ask.answered"]:
        answered_at.setdefault(event["payload"]["id"], event["ts"])
    durations = []
    for event in by_kind["ask.created"]:
        if not scope.admits(event["party"], event["project"]):
            continue
        answer_ts = answered_at.get(event["payload"]["id"])
        if answer_ts is None or not _since_cutoff(answer_ts, cutoff):
            continue
        durations.append(_seconds_between(event["ts"], answer_ts))
    return durations


def _totals(by_kind, scope, quests, merged_prs, cutoff):
    durations = _answer_seconds(by_kind, scope, cutoff)
    done_tasks = {
        (event["payload"]["quest"], event["payload"]["tid"])
        for event in by_kind["task.done"]
        if scope.admits(event["party"], event["project"]) and _since_cutoff(event["ts"], cutoff)
    }
    handoffs = sum(
        1
        for event in by_kind["party.handed_off"]
        if scope.admits(event["party"], event["project"]) and _since_cutoff(event["ts"], cutoff)
    )
    return {
        "quests_done": sum(1 for quest in quests if _since_cutoff(quest["done_at"], cutoff)),
        "prs_merged": sum(
            1
            for record in merged_prs
            if scope.admits(record["party"], record["project"]) and _since_cutoff(record["merged_at"], cutoff)
        ),
        "tasks_done": len(done_tasks),
        "asks_answered": len(durations),
        "median_answer_seconds": float(statistics.median(durations)) if durations else None,
        "handoffs": handoffs,
    }


def _last_output_line(output_tail):
    for line in reversed(output_tail.split("\n")):
        if line.strip():
            return line
    return ""


def _lifecycle_failure_detail(payload):
    if payload["status"] == "failed":
        return "exit {}".format(payload["exit_code"])
    return payload["status"]


def _lifecycle_failure_entry(event):
    payload = event["payload"]
    return {
        "project": event["project"],
        "event": payload["event"],
        "repo": payload["repo"],
        "status": payload["status"],
        "ts": event["ts"],
        "detail": _lifecycle_failure_detail(payload),
        "last_line": _last_output_line(payload["output_tail"]),
    }


def _lifecycle_failures(by_kind, scope):
    entries = [
        _lifecycle_failure_entry(event)
        for event in by_kind["lifecycle.ran"]
        if event["payload"]["status"] in _LIFECYCLE_FAILURE_STATUSES and scope.admits_project(event["project"])
    ]
    return sorted(entries, key=lambda entry: entry["ts"], reverse=True)


def _first_event_ts(by_kind):
    return _earliest(
        [event["ts"] for events in by_kind.values() for event in events]
    )


def _earliest(timestamps):
    if not timestamps:
        return None
    return min(timestamps, key=timeutil.from_iso)


def build_model(conn, now, party, raid, project, projects_dir):
    by_kind = _load_events(conn)
    scope = _Scope(party, project, _raid_parties(by_kind, raid))
    merged_prs = _merged_pr_records(by_kind)
    finished_quests = _all_quests(by_kind, merged_prs)
    marked_slugs = set(_first_marks(by_kind))
    every_quest = [quest for quest in finished_quests if quest["slug"] not in marked_slugs]
    quests = [quest for quest in every_quest if scope.admits(quest["party"], quest["project"])]
    return {
        "quests": quests,
        "active_quests": _active_quests(conn, by_kind, now, projects_dir, scope),
        "incomplete_quests": _incomplete_quests(by_kind, scope, finished_quests),
        "raids": _finished_raids(by_kind, now, scope, raid, every_quest, merged_prs),
        "lifecycle_failures": _lifecycle_failures(by_kind, scope),
        "totals": _totals(by_kind, scope, quests, merged_prs, None),
        "week_totals": _totals(by_kind, scope, quests, merged_prs, now - _WEEK),
        "since": _first_event_ts(by_kind),
    }


def format_duration(seconds):
    if seconds is None:
        return "unknown"
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return "{}d {}h".format(days, hours)
    if hours:
        return "{}h {}m".format(hours, minutes)
    if minutes:
        return "{}m".format(minutes)
    return "<1m"


def _date(iso):
    if iso is None:
        return "?"
    return timeutil.from_iso(iso).strftime("%Y-%m-%d %H:%M")


def _epic_label(epic, progress):
    if epic is None:
        return "no epic"
    if progress is None:
        return "epic {}".format(epic)
    return "epic {} {}% ({}/{})".format(epic, progress["percent"], progress["done"], progress["total"])


def _asks_label(quest):
    if quest["asks_raised"] is None:
        return "asks n/a"
    label = "asks {} raised, {} answered".format(quest["asks_raised"], quest["asks_answered"])
    if quest["median_answer_seconds"] is None:
        return label
    return "{}, median {}".format(label, format_duration(quest["median_answer_seconds"]))


def _quest_lines(quest):
    lines = [
        "  {} - {}".format(quest["slug"], quest["title"]),
        "    party {} | project {} | {}".format(
            quest["party"], quest["project"], _epic_label(quest["epic"], quest["epic_progress"])
        ),
        "    {} -> {} ({})".format(
            _date(quest["started_at"]), _date(quest["done_at"]), format_duration(quest["duration_seconds"])
        ),
        "    tasks {} done, {} blocked events | cards {} | PRs {} | handoffs {}".format(
            quest["tasks_done"],
            quest["tasks_blocked_events"],
            len(quest["jira_cards_done"]),
            len(quest["prs_merged"]),
            quest["handoffs"],
        ),
        "    {}".format(_asks_label(quest)),
    ]
    if quest["drift"]:
        lines.append("    accepted drift: {}".format(len(quest["drift"])))
    if not quest["snapshot"]:
        lines.append("    no snapshot (derived from events)")
    return lines


def _active_quest_lines(quest):
    tasks = quest["tasks"]
    return [
        "  {} - {}".format(quest["slug"], quest["title"]),
        "    party {} | project {} | {}".format(quest["party"], quest["project"], _epic_label(quest["epic"], None)),
        "    started {} ({} ago)".format(_date(quest["started_at"]), format_duration(quest["age_seconds"])),
        "    {}% ({}/{} done) | active {} | blocked {} | queued {}".format(
            quest["percent_done"], tasks["done"], tasks["total"], tasks["active"], tasks["blocked"], tasks["queued"]
        ),
    ]


def _incomplete_quest_lines(quest):
    return [
        "  {} - {}".format(quest["slug"], quest["title"]),
        "    party {} | project {}".format(quest["party"], quest["project"]),
        "    {} -> {} | marked {}".format(
            _date(quest["started_at"]), _date(quest["done_at"]), _date(quest["marked_at"])
        ),
        "    {} of {} tasks not done when marked".format(quest["tasks_not_done"], quest["tasks_total"]),
        "    reason: {}".format(quest["reason"]),
    ]


def _raid_lines(raid):
    return [
        "  {}".format(raid["name"]),
        "    {} -> {} ({})".format(
            _date(raid["started_at"]), _date(raid["ended_at"]), format_duration(raid["duration_seconds"])
        ),
        "    parties {}".format(", ".join(raid["parties"])),
        "    quests {} | PRs merged {} | pauses {}".format(
            ", ".join(quest["slug"] for quest in raid["quests"]) or "none",
            len(raid["prs_merged"]),
            raid["pauses"],
        ),
    ]


def _lifecycle_failure_line(entry):
    return "  {} lifecycle.{} {} ({}): {}".format(
        entry["project"], entry["event"], entry["status"], entry["detail"], entry["last_line"] or "no output"
    )


def _totals_line(totals):
    return "  quests {} | PRs merged {} | tasks {} | asks answered {} (median {}) | handoffs {}".format(
        totals["quests_done"],
        totals["prs_merged"],
        totals["tasks_done"],
        totals["asks_answered"],
        format_duration(totals["median_answer_seconds"]),
        totals["handoffs"],
    )


def render_lines(model):
    lines = ["In progress ({})".format(len(model["active_quests"]))]
    for quest in model["active_quests"]:
        lines.extend(_active_quest_lines(quest))
    lines.extend(["", "Completed quests ({})".format(len(model["quests"]))])
    for quest in model["quests"]:
        lines.extend(_quest_lines(quest))
    lines.extend(["", "Closed without completing ({})".format(len(model["incomplete_quests"]))])
    for quest in model["incomplete_quests"]:
        lines.extend(_incomplete_quest_lines(quest))
    lines.extend(["", "Finished raids ({})".format(len(model["raids"]))])
    for raid in model["raids"]:
        lines.extend(_raid_lines(raid))
    lines.extend(["", "Lifecycle failures ({})".format(len(model["lifecycle_failures"]))])
    for entry in model["lifecycle_failures"]:
        lines.append(_lifecycle_failure_line(entry))
    lines.extend(["", "Totals", _totals_line(model["totals"])])
    return lines


def run(ctx, party, raid, project):
    return render_lines(build_model(ctx.conn, ctx.now, party, raid, project, ctx.projects_dir))
