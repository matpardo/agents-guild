import json


def assistant_line(message_id, timestamp, model, input_tokens, cache_creation, cache_read, output_tokens):
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": timestamp,
            "requestId": "req-" + message_id,
            "message": {
                "id": message_id,
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                    "output_tokens": output_tokens,
                },
            },
        }
    )


def write_transcript(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines))


def append_transcript(path, lines):
    with path.open("a") as handle:
        handle.write("".join(line + "\n" for line in lines))
