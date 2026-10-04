import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


def _modules(root, package):
    return ["{}.{}".format(package, path.stem) for path in sorted((root / package).glob("test_*.py"))]


def _run_module(root, module):
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return module, completed.returncode, completed.stderr + completed.stdout


def _test_count(output):
    match = _RAN_RE.search(output)
    if match is None:
        return 0
    return int(match.group(1))


def run(root, package, jobs, out):
    modules = _modules(root, package)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda module: _run_module(root, module), modules))
    failed = [result for result in results if result[1] != 0]
    for module, _, output in failed:
        out.write("FAILED {}\n{}\n".format(module, output))
    total = sum(_test_count(output) for _, _, output in results)
    out.write("{} modules, {} tests, {} failed\n".format(len(modules), total, len(failed)))
    if failed:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    return run(root, "tests", args.jobs, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
