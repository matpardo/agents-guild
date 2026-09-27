#!/usr/bin/env python3
import json
import os
import sys


def _fixtures_dir():
    return os.environ["GUILD_TEST_GH_DIR"]


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
    sys.stderr.write("no fixture for " + name)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if args[:2] == ["pr", "view"]:
        number = args[2]
        repo_index = args.index("--repo") + 1
        repo = args[repo_index]
        _respond("view_{}_{}".format(repo.replace("/", "-"), number))
        return
    if args[:2] == ["pr", "list"]:
        head_index = args.index("--head") + 1
        branch = args[head_index]
        _respond("list_{}".format(branch.replace("/", "-")))
        return
    sys.stderr.write("fake gh: unhandled args {}".format(args))
    sys.exit(1)


if __name__ == "__main__":
    main()
