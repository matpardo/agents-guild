import json

from guild import events


def run(ctx, visibility):
    lines = []
    for event in events.all_events(ctx.conn):
        if event["visibility"] != visibility:
            continue
        record = {key: value for key, value in event.items() if key != "seq"}
        lines.append(json.dumps(record))
    return lines
