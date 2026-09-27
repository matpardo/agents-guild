def next_id(conn, table):
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next FROM {}".format(table)).fetchone()
    return row["next"]
