from guild import db, events, reducers, schema


def run(ctx):
    with db.writing(ctx.conn):
        schema.drop_projections(ctx.conn)
        all_events = events.all_events(ctx.conn)
        for event in all_events:
            reducers.apply(ctx.conn, event)
    return "rebuilt from {} events".format(len(all_events))
