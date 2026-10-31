import re


def card_known(ctx, project, project_config, key):
    if project is not None:
        row = ctx.conn.execute("SELECT key FROM cards WHERE project = ? AND key = ?", (project, key)).fetchone()
        if row is not None:
            return True
    if project_config is None:
        return False
    key_ref = (project_config.get("sdd") or {}).get("key_ref")
    if key_ref is None:
        return False
    return re.fullmatch(key_ref, key) is not None
