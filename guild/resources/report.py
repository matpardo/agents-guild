import os

from guild import config, timeutil
from guild.errors import GuildError
from guild.resources import docker

_CATEGORIES = (
    "worktree",
    "docker_container",
    "docker_image",
    "docker_volume",
    "claude_scratch",
    "claude_transcripts",
    docker.MARKER_CATEGORY,
)
_PATH_CATEGORIES = ("worktree", "claude_scratch", "claude_transcripts")
_FLAG_LABELS = {
    "merged": "merged, still on disk",
    "closed": "closed, still on disk",
    "orphaned": "orphaned",
    "dangling": "dangling",
    "unused": "unused",
}
_NOISE_BYTES = 1024 * 1024
_UNTRACKED_THRESHOLD_BYTES = 1024 * 1024 * 1024
_MAX_GROWERS = 5
_MAX_ITEMS_PER_CATEGORY = 10
_UNMEASURED_STATES = ("unavailable", "skipped")
_UNKNOWN = "?"
_NEW = "new"
_UNITS = ((10**12, "TB", 1), (10**9, "GB", 1), (10**6, "MB", 0), (10**3, "kB", 0))
_DOCKER_KEYS = ("images", "images_reclaimable", "containers", "volumes", "build_cache")
_DOCKER_TOTAL_KEYS = ("images", "containers", "volumes", "build_cache")
_UNATTRIBUTED_LABEL = "unattributed"
_ALL_ROWS = "1 = 1"
_NO_SAMPLES_LINE = "no samples yet; run guild resources collect"


def _bound(conn, table, aggregate, scope, params):
    row = conn.execute("SELECT {}(ts) AS ts FROM {} WHERE {}".format(aggregate, table, scope), params).fetchone()
    return row["ts"]


def _baseline_ts(conn, table, scope, params, latest, cutoff):
    at_cutoff = _bound(conn, table, "MAX", scope + " AND ts <= ?", params + [cutoff])
    if at_cutoff is not None:
        return None if at_cutoff == latest else at_cutoff, False
    oldest = _bound(conn, table, "MIN", scope, params)
    return None if oldest == latest else oldest, True


def _rows_at(conn, project_key, ts):
    rows = conn.execute(
        "SELECT category, item, bytes, state, flag, detail FROM resource_samples WHERE project = ? AND ts = ?",
        (project_key, ts),
    ).fetchall()
    return {(row["category"], row["item"]): dict(row) for row in rows}


def _item_growth(now_row, base_rows):
    base = base_rows.get((now_row["category"], now_row["item"]))
    if base is None:
        return now_row["bytes"]
    if now_row["bytes"] is None or base["bytes"] is None:
        return None
    return now_row["bytes"] - base["bytes"]


def _item_entry(now_row, base_rows):
    key = (now_row["category"], now_row["item"])
    is_new = base_rows is not None and key not in base_rows
    delta = None
    if base_rows is not None and not is_new:
        delta = _item_growth(now_row, base_rows)
    return {
        "category": now_row["category"],
        "item": now_row["item"],
        "bytes": now_row["bytes"],
        "delta_bytes": delta,
        "new": is_new,
        "state": now_row["state"],
        "flag": now_row["flag"],
        "detail": now_row["detail"],
    }


def _sum_present(values):
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _category_delta(category, now_rows, base_rows):
    keys = {key for key in now_rows if key[0] == category} | {key for key in base_rows if key[0] == category}
    contributions = []
    for key in keys:
        now_row = now_rows.get(key)
        base_row = base_rows.get(key)
        if now_row is None:
            contributions.append(-base_row["bytes"] if base_row["bytes"] is not None else None)
        elif base_row is None:
            contributions.append(now_row["bytes"])
        elif now_row["bytes"] is None or base_row["bytes"] is None:
            contributions.append(None)
        else:
            contributions.append(now_row["bytes"] - base_row["bytes"])
    return _sum_present(contributions)


def _category_state(rows):
    states = {row["state"] for row in rows}
    for state in _UNMEASURED_STATES:
        if state in states:
            return state
    return "ok"


def _category_entry(category, now_rows, base_rows):
    rows = [row for key, row in now_rows.items() if key[0] == category]
    detail = ""
    if category == docker.MARKER_CATEGORY:
        detail = rows[0]["detail"]
    delta = None
    if base_rows is not None:
        delta = _category_delta(category, now_rows, base_rows)
    return {
        "category": category,
        "bytes": _sum_present(row["bytes"] for row in rows),
        "delta_bytes": delta,
        "state": _category_state(rows),
        "detail": detail,
    }


def _growers(items):
    candidates = []
    for entry in items:
        growth = entry["bytes"] if entry["new"] else entry["delta_bytes"]
        if growth is not None and growth >= _NOISE_BYTES:
            candidates.append({"category": entry["category"], "item": entry["item"], "delta_bytes": growth})
    candidates.sort(key=lambda grower: (-grower["delta_bytes"], grower["category"], grower["item"]))
    return candidates[:_MAX_GROWERS]


def _sorted_items(entries):
    order = {category: index for index, category in enumerate(_CATEGORIES)}
    return sorted(entries, key=lambda entry: (order[entry["category"]], entry["item"]))


def _project_model(conn, project_key, cutoff_iso):
    scope = "project = ?"
    latest = _bound(conn, "resource_samples", "MAX", scope, [project_key])
    if latest is None:
        return None
    baseline, oldest = _baseline_ts(conn, "resource_samples", scope, [project_key], latest, cutoff_iso)
    now_rows = _rows_at(conn, project_key, latest)
    base_rows = None if baseline is None else _rows_at(conn, project_key, baseline)
    present_categories = [category for category in _CATEGORIES if any(key[0] == category for key in now_rows)]
    categories = [_category_entry(category, now_rows, base_rows) for category in present_categories]
    items = _sorted_items(
        [_item_entry(row, base_rows) for key, row in now_rows.items() if key[0] != docker.MARKER_CATEGORY]
    )
    deltas = [category["delta_bytes"] for category in categories]
    return {
        "sampled_at": latest,
        "baseline_at": baseline,
        "baseline_oldest": baseline is not None and oldest,
        "total_bytes": _sum_present(category["bytes"] for category in categories),
        "delta_bytes": None if baseline is None else _sum_present(deltas),
        "categories": categories,
        "items": items,
        "growers": _growers(items),
    }


def _machine_row(conn, ts):
    return conn.execute("SELECT * FROM resource_machine WHERE ts = ?", (ts,)).fetchone()


def _docker_totals(row):
    values = {key: row["docker_" + key] for key in _DOCKER_KEYS}
    if all(value is None for value in values.values()):
        return None
    values["total"] = _sum_present(values[key] for key in _DOCKER_TOTAL_KEYS)
    return values


def _disk_delta(row, base_row):
    if base_row is None or row["disk_used"] is None or base_row["disk_used"] is None:
        return None
    return row["disk_used"] - base_row["disk_used"]


def _disk_percent(row):
    if row["disk_used"] is None or not row["disk_total"]:
        return None
    return int(round(100 * row["disk_used"] / row["disk_total"]))


def _untracked_growth(disk_delta, tracked_deltas):
    present = [delta for delta in tracked_deltas if delta is not None]
    if disk_delta is None or not present:
        return None
    untracked = disk_delta - sum(present)
    if untracked < _UNTRACKED_THRESHOLD_BYTES:
        return None
    return untracked


def _machine_model(conn, cutoff_iso, tracked_deltas):
    latest = _bound(conn, "resource_machine", "MAX", _ALL_ROWS, [])
    if latest is None:
        return None
    baseline, _ = _baseline_ts(conn, "resource_machine", _ALL_ROWS, [], latest, cutoff_iso)
    row = _machine_row(conn, latest)
    base_row = None if baseline is None else _machine_row(conn, baseline)
    disk_delta = _disk_delta(row, base_row)
    return {
        "sampled_at": latest,
        "disk_total": row["disk_total"],
        "disk_used": row["disk_used"],
        "disk_percent": _disk_percent(row),
        "disk_delta": disk_delta,
        "mem_total": row["mem_total"],
        "mem_available": row["mem_available"],
        "guild_db_bytes": row["guild_db_bytes"],
        "docker": _docker_totals(row),
        "untracked_growth": _untracked_growth(disk_delta, tracked_deltas),
    }


def _known_names(conn, projects_dir):
    configured = {project["name"] for project in config.load_all_projects(projects_dir)}
    rows = conn.execute("SELECT DISTINCT project FROM resource_samples WHERE project != ''").fetchall()
    return configured | {row["project"] for row in rows}


def _require_known(conn, projects_dir, project):
    if project is None or project in _known_names(conn, projects_dir):
        return
    raise GuildError("unknown project '{}'".format(project), 1)


def _sampled_projects(conn, project):
    if project is not None:
        return [project]
    rows = conn.execute("SELECT DISTINCT project FROM resource_samples WHERE project != '' ORDER BY project").fetchall()
    return [row["project"] for row in rows]


def build_model(conn, now, project, since, projects_dir):
    cutoff_iso = timeutil.to_iso(now - timeutil.parse_duration(since))
    _require_known(conn, projects_dir, project)
    projects = []
    for name in _sampled_projects(conn, project):
        model = _project_model(conn, name, cutoff_iso)
        if model is not None:
            projects.append(dict(model, name=name))
    unattributed = None if project is not None else _project_model(conn, "", cutoff_iso)
    tracked = [model["delta_bytes"] for model in projects]
    if unattributed is not None:
        tracked.append(unattributed["delta_bytes"])
    return {
        "generated_at": timeutil.to_iso(now),
        "since": since,
        "machine": _machine_model(conn, cutoff_iso, tracked),
        "projects": projects,
        "unattributed": unattributed,
    }


def _human(size):
    for threshold, unit, decimals in _UNITS:
        if size >= threshold:
            return "{:.{}f} {}".format(size / threshold, decimals, unit)
    return "{} B".format(size)


def _signed(size):
    if size is None:
        return _UNKNOWN
    sign = "-" if size < 0 else "+"
    return "{}{}".format(sign, _human(abs(size)))


def _bytes_label(size):
    if size is None:
        return _UNKNOWN
    return _human(size)


def _age(now, ts):
    return timeutil.age_label(now, ts)


def _machine_lines(machine, since, now):
    disk = "disk n/a"
    if machine["disk_percent"] is not None:
        delta = ""
        if machine["disk_delta"] is not None:
            delta = ", {} in {}".format(_signed(machine["disk_delta"]), since)
        disk = "disk {}% used ({} of {}{})".format(
            machine["disk_percent"], _human(machine["disk_used"]), _human(machine["disk_total"]), delta
        )
    ram = "ram n/a"
    if machine["mem_available"] is not None:
        ram = "ram {} available of {}".format(_human(machine["mem_available"]), _human(machine["mem_total"]))
    docker_label = "docker n/a"
    if machine["docker"] is not None:
        docker_label = "docker {} (reclaimable {})".format(
            _bytes_label(machine["docker"]["total"]), _bytes_label(machine["docker"]["images_reclaimable"])
        )
    lines = [
        "machine   {}   {}".format(disk, ram),
        "          {}   guild.db {}   sampled {} ago".format(
            docker_label, _human(machine["guild_db_bytes"]), _age(now, machine["sampled_at"])
        ),
    ]
    if machine["untracked_growth"] is not None:
        tracked = machine["disk_delta"] - machine["untracked_growth"]
        lines.append(
            "untracked growth: {} (machine {}, tracked {})".format(
                _signed(machine["untracked_growth"]), _signed(machine["disk_delta"]), _signed(tracked)
            )
        )
    return lines


def _header(label, model, now):
    total = "total {}".format(_bytes_label(model["total_bytes"]))
    if model["baseline_at"] is None:
        return "{}   {}   no earlier sample   sampled {} ago".format(label, total, _age(now, model["sampled_at"]))
    if model["delta_bytes"] is not None:
        total += " ({})".format(_signed(model["delta_bytes"]))
    baseline = timeutil.issued_label(model["baseline_at"])
    if model["baseline_oldest"]:
        baseline += " (oldest available)"
    return "{}   {}   baseline {} (sampled {} ago)".format(label, total, baseline, _age(now, model["sampled_at"]))


def _category_line(category):
    if category["category"] == docker.MARKER_CATEGORY:
        return "  {:<18} {} ({})".format(category["category"], category["state"], category["detail"])
    text = _bytes_label(category["bytes"])
    if category["delta_bytes"] is not None:
        text += " ({})".format(_signed(category["delta_bytes"]))
    return "  {:<18} {}".format(category["category"], text)


def _delta_label(entry, has_baseline):
    if not has_baseline:
        return ""
    if entry["new"]:
        return _NEW
    return _signed(entry["delta_bytes"])


def _top_items(model, category):
    entries = [entry for entry in model["items"] if entry["category"] == category]
    entries.sort(key=lambda entry: (entry["bytes"] is None, -(entry["bytes"] or 0), entry["item"]))
    return entries[:_MAX_ITEMS_PER_CATEGORY], len(entries) - _MAX_ITEMS_PER_CATEGORY


def _item_columns(model):
    shown = []
    for category in model["categories"]:
        shown.extend(_top_items(model, category["category"])[0])
    has_baseline = model["baseline_at"] is not None
    return (
        max((len(entry["item"]) for entry in shown), default=0),
        max((len(_bytes_label(entry["bytes"])) for entry in shown), default=0),
        max((len(_delta_label(entry, has_baseline)) for entry in shown), default=0),
    )


def _item_line(entry, widths, has_baseline):
    item_width, bytes_width, delta_width = widths
    line = "    {}   {}   {}   {}".format(
        entry["item"].ljust(item_width),
        _bytes_label(entry["bytes"]).rjust(bytes_width),
        _delta_label(entry, has_baseline).ljust(delta_width),
        _FLAG_LABELS.get(entry["flag"], ""),
    )
    return line.rstrip()


def _grower_label(grower):
    name = grower["item"]
    if grower["category"] in _PATH_CATEGORIES:
        name = os.path.basename(name)
    return "{} {}".format(name, _signed(grower["delta_bytes"]))


def _project_lines(label, model, now):
    lines = [_header(label, model, now)]
    widths = _item_columns(model)
    has_baseline = model["baseline_at"] is not None
    for category in model["categories"]:
        lines.append(_category_line(category))
        if category["category"] == docker.MARKER_CATEGORY:
            continue
        entries, remainder = _top_items(model, category["category"])
        lines.extend(_item_line(entry, widths, has_baseline) for entry in entries)
        if remainder > 0:
            lines.append("    (+{} more)".format(remainder))
    if model["growers"]:
        lines.append("  top growers: {}".format(", ".join(_grower_label(grower) for grower in model["growers"])))
    return lines


def render(model, now):
    if model["machine"] is None:
        return [_NO_SAMPLES_LINE]
    sections = [(project["name"], project) for project in model["projects"]]
    if model["unattributed"] is not None:
        sections.append((_UNATTRIBUTED_LABEL, model["unattributed"]))
    lines = _machine_lines(model["machine"], model["since"], now)
    for label, section in sections:
        lines.append("")
        lines.extend(_project_lines(label, section, now))
    return lines
