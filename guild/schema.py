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
    "raid_pauses",
    "pr_shared_areas",
    "pr_files",
    "merge_queue_pins",
    "main_status",
    "session_status",
    "cost_samples",
    "resource_samples",
    "resource_machine",
    "leader_windows",
    "dispatch_decisions",
    "findings",
)

_RAID_MEMBERS_TABLE = """
    CREATE TABLE IF NOT EXISTS raid_members (
        raid TEXT NOT NULL,
        party TEXT NOT NULL,
        expires_at TEXT,
        lead INTEGER,
        PRIMARY KEY (raid, party)
    )
    """

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
        card TEXT,
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
    _RAID_MEMBERS_TABLE,
    """
    CREATE TABLE IF NOT EXISTS raid_pauses (
        raid TEXT PRIMARY KEY,
        paused_at TEXT NOT NULL,
        paused_by TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pr_shared_areas (
        repo TEXT NOT NULL,
        number INTEGER NOT NULL,
        glob TEXT NOT NULL,
        PRIMARY KEY (repo, number, glob)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pr_files (
        repo TEXT NOT NULL,
        number INTEGER NOT NULL,
        path TEXT NOT NULL,
        PRIMARY KEY (repo, number, path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        project TEXT NOT NULL,
        class TEXT NOT NULL,
        repo TEXT NOT NULL,
        number INTEGER NOT NULL,
        party TEXT,
        recorded_at TEXT NOT NULL,
        PRIMARY KEY (project, class, repo, number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS merge_queue_pins (
        first_repo TEXT NOT NULL,
        first_number INTEGER NOT NULL,
        second_repo TEXT NOT NULL,
        second_number INTEGER NOT NULL,
        party TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (first_repo, first_number, second_repo, second_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS main_status (
        repo TEXT NOT NULL,
        source TEXT NOT NULL,
        red INTEGER NOT NULL,
        reason TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (repo, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_status (
        session_id TEXT PRIMARY KEY,
        party TEXT NOT NULL,
        status TEXT NOT NULL,
        detail TEXT,
        since TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cost_samples (
        session_id TEXT NOT NULL,
        day TEXT NOT NULL,
        model TEXT NOT NULL,
        party TEXT NOT NULL,
        quest TEXT NOT NULL,
        tid TEXT NOT NULL,
        input_tokens INTEGER NOT NULL,
        cache_creation_tokens INTEGER NOT NULL,
        cache_read_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        PRIMARY KEY (session_id, day, model, party, quest, tid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_samples (
        project TEXT NOT NULL,
        ts TEXT NOT NULL,
        category TEXT NOT NULL,
        item TEXT NOT NULL,
        bytes INTEGER,
        state TEXT NOT NULL,
        flag TEXT NOT NULL,
        detail TEXT NOT NULL,
        PRIMARY KEY (project, ts, category, item)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_resource_samples_item
        ON resource_samples (project, category, item, ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_machine (
        ts TEXT PRIMARY KEY,
        disk_total INTEGER,
        disk_used INTEGER,
        mem_total INTEGER,
        mem_available INTEGER,
        guild_db_bytes INTEGER NOT NULL,
        docker_images INTEGER,
        docker_images_reclaimable INTEGER,
        docker_containers INTEGER,
        docker_volumes INTEGER,
        docker_build_cache INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leader_windows (
        party TEXT NOT NULL,
        generation INTEGER NOT NULL,
        window_id TEXT NOT NULL,
        PRIMARY KEY (party, generation)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dispatch_decisions (
        project TEXT NOT NULL,
        key TEXT NOT NULL,
        mode TEXT NOT NULL,
        rule TEXT NOT NULL,
        outcome TEXT NOT NULL,
        party TEXT,
        generation INTEGER,
        permission_mode TEXT,
        subject TEXT NOT NULL,
        reason TEXT,
        decided_at TEXT NOT NULL,
        window_id TEXT,
        state TEXT,
        PRIMARY KEY (project, key, mode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dispatch_cursors (
        project TEXT PRIMARY KEY,
        last_seq INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transcript_cursors (
        path TEXT PRIMARY KEY,
        offset INTEGER NOT NULL
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
    ("leaders", "cwd", "TEXT"),
    ("leaders", "permission_mode", "TEXT"),
    ("prs", "mergeable", "TEXT"),
    ("prs", "review_decision", "TEXT"),
    ("prs", "merge_state", "TEXT"),
    ("prs", "base_branch", "TEXT"),
    ("prs", "unresolved_threads", "INTEGER"),
    ("prs", "review_comment_count", "INTEGER"),
    ("prs", "last_notified_comment_count", "INTEGER"),
    ("prs", "last_activity_at", "TEXT"),
    ("notices", "announces", "TEXT"),
    ("notices", "seen_at", "TEXT"),
    ("raid_members", "lead", "INTEGER"),
    ("prs", "additions", "INTEGER"),
    ("prs", "deletions", "INTEGER"),
    ("prs", "created_at", "TEXT"),
    ("prs", "checks_pending", "INTEGER"),
    ("prs", "needs_ask_answer", "INTEGER"),
    ("prs", "needs_human_pr_review", "INTEGER"),
    ("prs", "card", "TEXT"),
    ("asks", "snapshot", "TEXT"),
    ("asks", "answered_at", "TEXT"),
    ("leaders", "handoff_consumed_at", "TEXT"),
    ("parties", "keeper", "INTEGER"),
    ("prs", "fixes_main", "INTEGER"),
    ("prs", "fixes_flaky", "INTEGER"),
    ("prs", "blocked_external", "TEXT"),
    ("prs", "head_sha", "TEXT"),
    ("prs", "fix_requested_sha", "TEXT"),
)


def _existing_columns(conn, table):
    rows = conn.execute("PRAGMA table_info({})".format(table)).fetchall()
    return {row["name"] for row in rows}


def _add_column_if_missing(conn, table, column, ddl_type):
    if column in _existing_columns(conn, table):
        return
    conn.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, column, ddl_type))


def _raid_expiry_is_not_null(conn):
    rows = conn.execute("PRAGMA table_info(raid_members)").fetchall()
    return any(row["name"] == "expires_at" and row["notnull"] for row in rows)


def _rebuild_raid_members(conn):
    conn.execute("ALTER TABLE raid_members RENAME TO raid_members_legacy")
    conn.execute(_RAID_MEMBERS_TABLE)
    conn.execute(
        "INSERT INTO raid_members (raid, party, expires_at)"
        " SELECT raid, party, expires_at FROM raid_members_legacy"
    )
    conn.execute("DROP TABLE raid_members_legacy")


def _relax_raid_expiry(conn):
    if not _raid_expiry_is_not_null(conn):
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        if _raid_expiry_is_not_null(conn):
            _rebuild_raid_members(conn)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _split_needs_human(conn):
    conn.execute(
        "UPDATE prs SET lifecycle = 'draft', needs_ask_answer = 1 WHERE lifecycle = 'needs-human'"
    )
    conn.execute("UPDATE prs SET needs_ask_answer = 0 WHERE needs_ask_answer IS NULL")
    conn.execute("UPDATE prs SET needs_human_pr_review = 0 WHERE needs_human_pr_review IS NULL")


def _default_fix_marks(conn):
    conn.execute("UPDATE prs SET fixes_main = 0 WHERE fixes_main IS NULL")
    conn.execute("UPDATE prs SET fixes_flaky = 0 WHERE fixes_flaky IS NULL")


def create_all(conn):
    for statement in _CREATE_STATEMENTS:
        conn.execute(statement)
    _relax_raid_expiry(conn)
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        _add_column_if_missing(conn, table, column, ddl_type)
    _split_needs_human(conn)
    _default_fix_marks(conn)


def drop_projections(conn):
    for table in PROJECTION_TABLES:
        conn.execute("DELETE FROM {}".format(table))
