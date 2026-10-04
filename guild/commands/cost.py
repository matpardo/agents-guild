from guild import cost_collect, timeutil

_UNBOUND = "unbound"
_NONE_LABEL = "-"
_MILLION = 1000000
_HEADERS = ("input", "cache write", "cache read", "output")
_GROUPS = {
    "session": "cost_samples.session_id AS session_id",
    "party": "cost_samples.party AS party",
    "model": "cost_samples.model AS model",
    "quest": "cost_samples.quest AS quest",
    "task": "cost_samples.quest AS quest, cost_samples.tid AS tid",
}
_GROUP_BY = {
    "session": "cost_samples.session_id",
    "party": "cost_samples.party",
    "model": "cost_samples.model",
    "quest": "cost_samples.quest",
    "task": "cost_samples.quest, cost_samples.tid",
}
_SUM_COLUMNS = (
    "SUM(input_tokens) AS input_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,"
    " SUM(cache_read_tokens) AS cache_read_tokens, SUM(output_tokens) AS output_tokens"
)


def _where_clause(since, now, project):
    conditions = []
    params = []
    if since is not None:
        cutoff = (now - timeutil.parse_duration(since)).date().isoformat()
        conditions.append("cost_samples.day >= ?")
        params.append(cutoff)
    if project is not None:
        conditions.append("parties.project = ?")
        params.append(project)
    if not conditions:
        return "", params
    return " WHERE " + " AND ".join(conditions), params


def _label(by, row):
    if by == "party":
        return row["party"] or _UNBOUND
    if by == "task":
        if not row["quest"]:
            return _NONE_LABEL
        return "{}/{}".format(row["quest"], row["tid"])
    if by == "quest":
        return row["quest"] or _NONE_LABEL
    if by == "model":
        return row["model"]
    return row["session_id"]


def _query(ctx, since, by, project):
    where, params = _where_clause(since, ctx.now, project)
    sql = (
        "SELECT {keys}, {sums} FROM cost_samples"
        " LEFT JOIN parties ON parties.name = cost_samples.party{where}"
        " GROUP BY {group}"
    ).format(keys=_GROUPS[by], sums=_SUM_COLUMNS, where=where, group=_GROUP_BY[by])
    return ctx.conn.execute(sql, params).fetchall()


def _counts(row):
    return (
        row["input_tokens"],
        row["cache_creation_tokens"],
        row["cache_read_tokens"],
        row["output_tokens"],
    )


def _millions(value):
    return "{:.3f}".format(value / _MILLION)


def _format_table(by, entries):
    totals = [sum(counts[index] for _, counts in entries) for index in range(len(_HEADERS))]
    body = [(label, [_millions(value) for value in counts]) for label, counts in entries]
    body.append(("total", [_millions(value) for value in totals]))
    key_width = max(len(by), max(len(label) for label, _ in body))
    widths = [
        max(len(header), max(len(cells[index]) for _, cells in body))
        for index, header in enumerate(_HEADERS)
    ]
    header_line = by.ljust(key_width) + "".join(
        "  " + header.rjust(width) for header, width in zip(_HEADERS, widths)
    )
    lines = [header_line]
    for label, cells in body:
        lines.append(
            label.ljust(key_width) + "".join("  " + cell.rjust(width) for cell, width in zip(cells, widths))
        )
    return lines


def run(ctx, since, by, project):
    cost_collect.collect(ctx)
    rows = _query(ctx, since, by, project)
    if not rows:
        return ["no cost data"]
    entries = [(_label(by, row), _counts(row)) for row in rows]
    entries.sort(key=lambda entry: (-sum(entry[1]), entry[0]))
    return _format_table(by, entries)
