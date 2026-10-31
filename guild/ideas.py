def linked_ideas(ctx, party):
    return ctx.conn.execute(
        "SELECT ideas.id AS id, ideas.title AS title FROM idea_links"
        " JOIN ideas ON ideas.id = idea_links.idea_id WHERE idea_links.party = ? ORDER BY ideas.id ASC",
        (party,),
    ).fetchall()


def linked_ideas_for_adventurer(ctx, adventurer_id):
    return ctx.conn.execute(
        "SELECT ideas.id AS id, ideas.title AS title FROM idea_adventurer_links"
        " JOIN ideas ON ideas.id = idea_adventurer_links.idea_id WHERE idea_adventurer_links.adventurer = ?"
        " ORDER BY ideas.id ASC",
        (adventurer_id,),
    ).fetchall()
