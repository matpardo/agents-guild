#!/usr/bin/env python3
import hashlib
import os
import sys


def _fixtures_dir():
    return os.environ["GUILD_TEST_ACLI_DIR"]


def fixture_name(jql):
    return hashlib.sha256(jql.encode()).hexdigest()


def _respond(name):
    directory = _fixtures_dir()
    ok_path = os.path.join(directory, name + ".json")
    err_path = os.path.join(directory, name + ".err")
    if os.path.isfile(err_path):
        sys.stderr.write(open(err_path).read())
        sys.exit(1)
    if os.path.isfile(ok_path):
        sys.stdout.write(open(ok_path).read())
        sys.exit(0)
    sys.stderr.write("no fixture for jql: " + name)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if args[:3] == ["jira", "workitem", "search"]:
        jql_index = args.index("--jql") + 1
        jql = args[jql_index]
        _respond(fixture_name(jql))
        return
    sys.stderr.write("fake acli: unhandled args {}".format(args))
    sys.exit(1)


if __name__ == "__main__":
    main()
