import json
from collections import namedtuple
from datetime import timezone

from guild.timeutil import from_iso

UsageMessage = namedtuple(
    "UsageMessage", ("timestamp", "model", "input", "cache_creation", "cache_read", "output")
)

_SYNTHETIC_MODEL = "<synthetic>"


def _parse_timestamp(text):
    if not isinstance(text, str):
        return None
    try:
        moment = from_iso(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _token_count(usage, field):
    value = usage.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _decode(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _chunk_from(record, timestamp):
    if not isinstance(record, dict) or record.get("type") != "assistant":
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    model = message.get("model")
    message_id = message.get("id")
    if not isinstance(usage, dict) or not isinstance(model, str) or model == _SYNTHETIC_MODEL:
        return None
    if not isinstance(message_id, str):
        return None
    counts = (
        _token_count(usage, "input_tokens"),
        _token_count(usage, "cache_creation_input_tokens"),
        _token_count(usage, "cache_read_input_tokens"),
        _token_count(usage, "output_tokens"),
    )
    return message_id, UsageMessage(timestamp, model, *counts)


def _merge(existing, chunk):
    return UsageMessage(
        existing.timestamp,
        existing.model,
        max(existing.input, chunk.input),
        max(existing.cache_creation, chunk.cache_creation),
        max(existing.cache_read, chunk.cache_read),
        max(existing.output, chunk.output),
    )


def _is_all_zero(message):
    return not (message.input or message.cache_creation or message.cache_read or message.output)


def scan(path, offset, cutoff):
    merged = {}
    next_offset = offset
    with path.open("rb") as handle:
        handle.seek(offset)
        while True:
            raw = handle.readline()
            if not raw.endswith(b"\n"):
                break
            record = _decode(raw)
            timestamp = _parse_timestamp(record.get("timestamp")) if isinstance(record, dict) else None
            if timestamp is not None and timestamp > cutoff:
                break
            next_offset += len(raw)
            if timestamp is None:
                continue
            parsed = _chunk_from(record, timestamp)
            if parsed is None:
                continue
            message_id, chunk = parsed
            if message_id in merged:
                merged[message_id] = _merge(merged[message_id], chunk)
                continue
            merged[message_id] = chunk
    messages = [message for message in merged.values() if not _is_all_zero(message)]
    return messages, next_offset
