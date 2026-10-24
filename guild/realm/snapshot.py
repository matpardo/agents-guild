from guild import config, timeutil
from guild.commands import main_status as main_status_commands
from guild.realm import status

_CLOSED_PR_LIFECYCLES = ("merged", "closed")


def _scalar(conn, sql, parameters):
    return conn.execute(sql, parameters).fetchone()[0]


def _project_entry(conn, project, red_repos):
    name = project["name"]
    repos = project["github"]["repos"]
    pr_lifecycles = [
        row["lifecycle"]
        for row in conn.execute("SELECT repo, lifecycle FROM prs").fetchall()
        if row["repo"] in repos and row["lifecycle"] not in _CLOSED_PR_LIFECYCLES
    ]
    return {
        "name": name,
        "parties": _scalar(conn, "SELECT COUNT(*) FROM parties WHERE project = ? AND state != 'closed'", (name,)),
        "open_quests": _scalar(conn, "SELECT COUNT(*) FROM quests WHERE project = ? AND state = 'active'", (name,)),
        "open_prs": len(pr_lifecycles),
        "ready_prs": pr_lifecycles.count("ready"),
        "open_asks": _scalar(
            conn,
            "SELECT COUNT(*) FROM asks JOIN parties ON parties.name = asks.party"
            " WHERE parties.project = ? AND asks.state = 'open'",
            (name,),
        ),
        "main_red": any(repo in red_repos for repo in repos),
    }


def build(ctx, guild_name):
    red_repos = {row["repo"] for row in main_status_commands.red_rows(ctx.conn) if row["external"] is None}
    snapshot = {
        "guild": guild_name,
        "generated_at": timeutil.to_iso(ctx.now),
        "projects": [
            _project_entry(ctx.conn, project, red_repos) for project in config.load_all_projects(ctx.projects_dir)
        ],
    }
    return status.validate(snapshot, False)
