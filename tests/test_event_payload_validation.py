import ast
import datetime
import sqlite3
import unittest
from pathlib import Path

from guild import events, reducers, schema
from guild.errors import GuildError

_REDUCERS_SOURCE = Path(reducers.__file__)


def _record(conn, kind, payload):
    now = datetime.datetime(2026, 10, 31, tzinfo=datetime.timezone.utc)
    return events.record(conn, now, "test", "alpha", "sess-1", "acme", kind, "public", payload)


def _payload_key(node):
    if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Constant):
        return None
    holder = node.value
    is_payload_name = _is_payload(holder)
    is_event_payload = (
        isinstance(holder, ast.Subscript)
        and isinstance(holder.value, ast.Name)
        and holder.value.id == "event"
        and isinstance(holder.slice, ast.Constant)
        and holder.slice.value == "payload"
    )
    if is_payload_name or is_event_payload:
        return node.slice.value
    return None


def _is_payload(node):
    return isinstance(node, ast.Name) and node.id == "payload"


def _guarded_key(node):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and _is_payload(node.func.value)
        and isinstance(node.args[0], ast.Constant)
    ):
        return node.args[0].value
    if (
        isinstance(node, ast.Compare)
        and isinstance(node.ops[0], ast.In)
        and _is_payload(node.comparators[0])
        and isinstance(node.left, ast.Constant)
    ):
        return node.left.value
    return None


def _required_keys(function, functions):
    keys = set()
    guarded = set()
    pending = [function]
    visited = set()
    while pending:
        current = pending.pop()
        if current.name in visited:
            continue
        visited.add(current.name)
        for node in ast.walk(current):
            key = _payload_key(node)
            if key is not None:
                keys.add(key)
            guarded_key = _guarded_key(node)
            if guarded_key is not None:
                guarded.add(guarded_key)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions:
                pending.append(functions[node.func.id])
    return keys - guarded


class RecordValidationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        schema.create_all(self.conn)

    def event_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def test_missing_key_is_refused_and_nothing_is_written(self):
        with self.assertRaises(GuildError) as raised:
            _record(self.conn, "claim.released", {"project": "acme"})
        self.assertIn("claim.released", raised.exception.message)
        self.assertIn("area", raised.exception.message)
        self.assertEqual(self.event_count(), 0)

    def test_unknown_kind_is_refused_and_nothing_is_written(self):
        with self.assertRaises(GuildError) as raised:
            _record(self.conn, "no.such_kind", {})
        self.assertIn("no.such_kind", raised.exception.message)
        self.assertEqual(self.event_count(), 0)

    def test_complete_payload_is_recorded(self):
        _record(self.conn, "claim.released", {"project": "acme", "area": "ci"})
        self.assertEqual(self.event_count(), 1)


class RequiredKeysTableTests(unittest.TestCase):
    def test_table_matches_the_keys_each_reducer_subscripts(self):
        tree = ast.parse(_REDUCERS_SOURCE.read_text())
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for kind, reducer in reducers._REDUCERS.items():
            with self.subTest(kind=kind):
                expected = _required_keys(functions[reducer.__name__], functions)
                self.assertEqual(set(reducers.required_keys(kind)), expected)


if __name__ == "__main__":
    unittest.main()
