from guild import timeutil


def member_raids(conn, now, party):
    rows = conn.execute("SELECT * FROM raid_members WHERE party = ?", (party,)).fetchall()
    return [row for row in rows if not timeutil.is_expired(now, row["expires_at"])]


def member_raid_names(conn, now, party):
    if party is None:
        return set()
    return {row["raid"] for row in member_raids(conn, now, party)}


def pause_row(conn, raid_name):
    return conn.execute("SELECT * FROM raid_pauses WHERE raid = ?", (raid_name,)).fetchone()


def paused_member_raids(conn, now, party):
    if party is None:
        return []
    rows = [pause_row(conn, name) for name in sorted(member_raid_names(conn, now, party))]
    return [row for row in rows if row is not None]
