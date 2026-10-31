import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUILD = ROOT / "guild"


def _module_name(path):
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _known_modules():
    return {_module_name(path) for path in GUILD.rglob("*.py")}


def _imports(path, known):
    targets = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names if alias.name in known)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module in known:
                targets.add(node.module)
            for alias in node.names:
                candidate = node.module + "." + alias.name
                if candidate in known:
                    targets.add(candidate)
    return targets


def _graph():
    known = _known_modules()
    return {_module_name(path): _imports(path, known) for path in GUILD.rglob("*.py")}


def _components(graph):
    index = {}
    low = {}
    stack = []
    on_stack = set()
    found = []
    counter = [0]

    def visit(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in index:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], index[target])
        if low[node] != index[node]:
            return
        component = []
        while True:
            member = stack.pop()
            on_stack.discard(member)
            component.append(member)
            if member == node:
                break
        found.append(sorted(component))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return found


class ImportCycleTest(unittest.TestCase):
    def test_guild_modules_have_no_import_cycle(self):
        cycles = [component for component in _components(_graph()) if len(component) > 1]
        self.assertEqual([], cycles, "import cycles: " + "; ".join(" <-> ".join(c) for c in cycles))


if __name__ == "__main__":
    unittest.main()
