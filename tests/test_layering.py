import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUILD = ROOT / "guild"
COMMANDS = "guild.commands"
ALLOWED_FILES = {GUILD / "cli.py", GUILD / "webserver.py"}
ALLOWED_DIR = GUILD / "commands"


def _commands_imports(path):
    targets = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names if _is_commands(alias.name))
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if _is_commands(node.module):
                targets.add(node.module)
            if node.module == "guild":
                targets.update(f"guild.{alias.name}" for alias in node.names if alias.name == "commands")
    return targets


def _is_commands(name):
    return name == COMMANDS or name.startswith(COMMANDS + ".")


def _is_allowed(path):
    return path in ALLOWED_FILES or ALLOWED_DIR in path.parents


class LayeringTest(unittest.TestCase):
    def test_core_modules_do_not_import_commands(self):
        offenders = []
        for path in sorted(GUILD.rglob("*.py")):
            if _is_allowed(path):
                continue
            for target in sorted(_commands_imports(path)):
                offenders.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual([], offenders, "core modules import guild.commands:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
