from guild import names
from guild.errors import GuildError

HUMAN_LABEL = "human"
UNBOUND_SESSION_LABEL = "unbound session"

ADVENTURER_LABEL = "adventurer {}"

UNBOUND_HINT = (
    "session not bound: continuing a party's work \u2192 `guild party resume <party>`;"
    " otherwise, when the work will change a repo, pick yourself: one PR job \u2192"
    ' `guild adventurer start "<job>" --task <epic>/<tid> --reason "<why>"`, several PRs \u2192'
    ' `guild party start <name> --reason "<why>"`; ask the human only when unsure;'
    " questions and commands stay unbound"
)
ADVENTURER_REFUSAL = "adventurers do one job; quests and tasks belong to parties"


def adventurer_label(adventurer_id):
    return ADVENTURER_LABEL.format(adventurer_id)


def resolve_adventurer(conn, session_id):
    if session_id is None:
        return None
    return conn.execute(
        "SELECT id, project, job, task FROM adventurers WHERE session_id = ? AND state = 'active' ORDER BY id DESC",
        (session_id,),
    ).fetchone()


def resolve_binding(conn, session_id):
    if session_id is None:
        return None
    row = conn.execute(
        "SELECT parties.name AS name, parties.project AS project, parties.generation AS generation"
        " FROM parties LEFT JOIN leaders ON leaders.party = parties.name AND leaders.generation = parties.generation"
        " WHERE parties.leader_session_id = ? AND parties.state = 'active'"
        " ORDER BY leaders.started_at DESC, parties.name",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return {"party": row["name"], "project": row["project"], "generation": row["generation"]}


def double_bindings(conn, project):
    rows = conn.execute(
        "SELECT leader_session_id, GROUP_CONCAT(name, ', ') AS names, COUNT(*) AS total FROM"
        " (SELECT leader_session_id, name FROM parties WHERE state = 'active'"
        " AND (? IS NULL OR project = ?) ORDER BY name)"
        " GROUP BY leader_session_id HAVING total > 1 ORDER BY names",
        (project, project),
    ).fetchall()
    return ["session leads {} active parties: {}".format(row["total"], row["names"]) for row in rows]


def require_binding(conn, session_id):
    binding = resolve_binding(conn, session_id)
    if binding is not None:
        return binding
    if resolve_adventurer(conn, session_id) is not None:
        raise GuildError(ADVENTURER_REFUSAL, 1)
    raise GuildError(UNBOUND_HINT, 1)


def require_actor(conn, session_id):
    adventurer = resolve_adventurer(conn, session_id)
    if adventurer is not None:
        return adventurer_label(adventurer["id"])
    return require_binding(conn, session_id)["party"]


def cursor_key(session_id):
    if session_id is None:
        return "human"
    return names.safe_key(session_id)


def resolve_actor(conn, session_id):
    if session_id is None:
        return None, False
    binding = resolve_binding(conn, session_id)
    if binding is not None:
        return binding["party"], False
    adventurer = resolve_adventurer(conn, session_id)
    if adventurer is not None:
        return adventurer_label(adventurer["id"]), False
    return None, True


def actor_label(party, unbound):
    if party is not None:
        return party
    if unbound:
        return UNBOUND_SESSION_LABEL
    return HUMAN_LABEL
