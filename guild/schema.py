PROJECTION_TABLES = (
    "parties",
    "leaders",
    "quests",
    "quest_tasks",
    "epics",
    "tasks",
    "prs",
    "cards",
    "asks",
    "notices",
    "claims",
    "raid_members",
)

_CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT UNIQUE NOT NULL,
        ts TEXT NOT NULL,
        origin TEXT NOT NULL,
        party TEXT,
        session_id TEXT,
        project TEXT,
        kind TEXT NOT NULL,
        visibility TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parties (
        name TEXT PRIMARY KEY,
        project TEXT,
        leader_session_id TEXT,
        generation INTEGER NOT NULL,
        state TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leaders (
        party TEXT NOT NULL,
        generation INTEGER NOT NULL,
        session_id TEXT,
        session_name TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        PRIMARY KEY (party, generation)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quests (
        slug TEXT PRIMARY KEY,
        project TEXT,
        party TEXT NOT NULL,
        epic TEXT,
        title TEXT NOT NULL,
        state TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_tasks (
        quest TEXT NOT NULL,
        tid TEXT NOT NULL,
        title TEXT NOT NULL,
        state TEXT NOT NULL,
        summary TEXT,
        blocked_reason TEXT,
        PRIMARY KEY (quest, tid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS epics (
        project TEXT NOT NULL,
        epic TEXT NOT NULL,
        title TEXT,
        jira_key TEXT,
        sdd_path TEXT,
        sdd_status TEXT,
        PRIMARY KEY (project, epic)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        project TEXT NOT NULL,
        epic TEXT NOT NULL,
        tid TEXT NOT NULL,
        title TEXT NOT NULL,
        jira_key TEXT,
        deps TEXT NOT NULL,
        order_idx INTEGER,
        sdd_status TEXT NOT NULL,
        PRIMARY KEY (project, epic, tid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prs (
        repo TEXT NOT NULL,
        number INTEGER NOT NULL,
        party TEXT NOT NULL,
        task_quest TEXT,
        task_tid TEXT,
        what TEXT NOT NULL,
        waits TEXT,
        lifecycle TEXT NOT NULL,
        branch TEXT,
        title TEXT,
        gh_state TEXT,
        gh_draft INTEGER,
        checks_failing INTEGER,
        checks_passing INTEGER,
        seeded INTEGER NOT NULL,
        synced_at TEXT,
        PRIMARY KEY (repo, number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cards (
        project TEXT NOT NULL,
        key TEXT NOT NULL,
        status TEXT NOT NULL,
        status_category TEXT NOT NULL,
        issue_type TEXT NOT NULL,
        parent_key TEXT,
        PRIMARY KEY (project, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asks (
        id INTEGER PRIMARY KEY,
        party TEXT NOT NULL,
        question TEXT NOT NULL,
        context TEXT NOT NULL,
        refs TEXT NOT NULL,
        options TEXT NOT NULL,
        state TEXT NOT NULL,
        answer TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY,
        party TEXT,
        scope TEXT NOT NULL,
        text TEXT NOT NULL,
        until_condition TEXT,
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claims (
        project TEXT NOT NULL,
        area TEXT NOT NULL,
        party TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY (project, area)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raid_members (
        raid TEXT NOT NULL,
        party TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY (raid, party)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cursors (
        session_id TEXT PRIMARY KEY,
        last_seq INTEGER NOT NULL
    )
    """,
)

_COLUMN_MIGRATIONS = (
    ("leaders", "handoff_path", "TEXT"),
    ("prs", "mergeable", "TEXT"),
    ("prs", "review_comment_count", "INTEGER"),
    ("prs", "last_notified_comment_count", "INTEGER"),
    ("prs", "last_activity_at", "TEXT"),
    ("notices", "announces", "TEXT"),
)


def _existing_columns(conn, table):
    rows = conn.execute("PRAGMA table_info({})".format(table)).fetchall()
    return {row["name"] for row in rows}


def _add_column_if_missing(conn, table, column, ddl_type):
    if column in _existing_columns(conn, table):
        return
    conn.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, column, ddl_type))


def create_all(conn):
    for statement in _CREATE_STATEMENTS:
        conn.execute(statement)
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        _add_column_if_missing(conn, table, column, ddl_type)


def drop_projections(conn):
    for table in PROJECTION_TABLES:
        conn.execute("DELETE FROM {}".format(table))
