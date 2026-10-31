def linked_ideas(ctx, party):
    return ctx.conn.execute(
        "SELECT ideas.id AS id, ideas.title AS title FROM idea_links"
        " JOIN ideas ON ideas.id = idea_links.idea_id WHERE idea_links.party = ? ORDER BY ideas.id ASC",
        (party,),
    ).fetchall()
