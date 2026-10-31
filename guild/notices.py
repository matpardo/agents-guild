from guild import timeutil


def active_notices(conn, now):
    rows = conn.execute("SELECT * FROM notices WHERE state = 'active' ORDER BY created_at DESC, id DESC").fetchall()
    result = []
    for row in rows:
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        result.append(row)
    return result


def targeting(rows, project, scope_guild_always, raid_member_of):
    matched = []
    for row in rows:
        if row["scope"] == "guild" and scope_guild_always:
            matched.append(row)
        elif project is not None and row["scope"] == "project:{}".format(project):
            matched.append(row)
        elif row["scope"].startswith(RAID_SCOPE_PREFIX) and row["scope"][len(RAID_SCOPE_PREFIX) :] in raid_member_of:
            matched.append(row)
    return matched


RAID_SCOPE_PREFIX = "raid:"
