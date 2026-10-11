OPEN_ASK_ID_SQL = (
    "(SELECT MIN(asks.id) FROM asks WHERE asks.state = 'open'"
    " AND instr(asks.refs, '\"pr:' || prs.repo || '#' || prs.number || '\"') > 0) AS open_ask_id"
)

PRS_WITH_ASK_SQL = "SELECT prs.*, " + OPEN_ASK_ID_SQL + " FROM prs"


def needs_answer(row):
    return bool(row["needs_ask_answer"]) or row["open_ask_id"] is not None
