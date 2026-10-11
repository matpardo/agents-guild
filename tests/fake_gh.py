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


def _respond_graphql(name):
    if not os.path.isfile(os.path.join(_fixtures_dir(), name + ".json")) and not os.path.isfile(
        os.path.join(_fixtures_dir(), name + ".err")
    ):
        sys.stdout.write(json.dumps(_threads_response([])))
        sys.exit(0)
    _respond(name)


def _threads_response(resolved_flags):
    nodes = [{"isResolved": flag} for flag in resolved_flags]
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}


def main():
    args = sys.argv[1:]
    if args[:2] == ["pr", "view"]:
        number = args[2]
        repo_index = args.index("--repo") + 1
        repo = args[repo_index]
        json_index = args.index("--json") + 1
        fields = args[json_index]
        prefix = "view_files" if "files" in fields.split(",") else "view"
        _respond("{}_{}_{}".format(prefix, repo.replace("/", "-"), number))
        return
    if args[:2] == ["pr", "ready"]:
        repo = args[args.index("--repo") + 1]
        with open(os.path.join(_fixtures_dir(), "ready_calls.log"), "a") as log:
            log.write("{} {}\n".format(repo, args[2]))
        _respond("ready_{}_{}".format(repo.replace("/", "-"), args[2]))
        return
    if args[:2] == ["pr", "list"] and "--repo" in args:
        repo = args[args.index("--repo") + 1]
        _respond("open_{}".format(repo.replace("/", "-")))
        return
    if args[:2] == ["pr", "list"]:
        head_index = args.index("--head") + 1
        branch = args[head_index]
        _respond("list_{}".format(branch.replace("/", "-")))
        return
    if args[:2] == ["api", "graphql"]:
        values = dict(arg.split("=", 1) for arg in args if "=" in arg and not arg.startswith("query="))
        _respond_graphql("threads_{}-{}_{}".format(values["owner"], values["name"], values["number"]))
        return
    if args[:1] == ["api"]:
        parts = args[1].split("/")
        repo = "-".join(parts[1:3])
        branch = "-".join(parts[4:-1])
        _respond("branch_checks_{}_{}".format(repo, branch))
        return
    sys.stderr.write("fake gh: unhandled args {}".format(args))
    sys.exit(1)


if __name__ == "__main__":
    main()
