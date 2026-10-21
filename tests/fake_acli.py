#!/usr/bin/env python3
import hashlib
import os
import subprocess
import sys


def fixture_name(jql):
    return hashlib.sha256(jql.encode()).hexdigest()


def _respond(directory, name):
    ok_path = os.path.join(directory, name + ".json")
    err_path = os.path.join(directory, name + ".err")
    if os.path.isfile(err_path):
        with open(err_path) as handle:
            return subprocess.CompletedProcess([], 1, "", handle.read())
    if os.path.isfile(ok_path):
        with open(ok_path) as handle:
            return subprocess.CompletedProcess([], 0, handle.read(), "")
    return subprocess.CompletedProcess([], 1, "", "no fixture for jql: " + name)


def respond(directory, args):
    if args[:3] == ["jira", "workitem", "search"]:
        jql = args[args.index("--jql") + 1]
        return _respond(directory, fixture_name(jql))
    return subprocess.CompletedProcess([], 1, "", "fake acli: unhandled args {}".format(args))


def main():
    result = respond(os.environ["GUILD_TEST_ACLI_DIR"], sys.argv[1:])
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
