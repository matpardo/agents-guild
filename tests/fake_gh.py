#!/usr/bin/env python3
import json
import os
import subprocess
import sys


def _respond(directory, name):
    ok_path = os.path.join(directory, name + ".json")
    err_path = os.path.join(directory, name + ".err")
    if os.path.isfile(err_path):
        with open(err_path) as handle:
            return subprocess.CompletedProcess([], 1, "", handle.read())
    if os.path.isfile(ok_path):
        with open(ok_path) as handle:
            return subprocess.CompletedProcess([], 0, handle.read(), "")
    return subprocess.CompletedProcess([], 1, "", "no fixture for " + name)


def _respond_graphql(directory, name):
    if not os.path.isfile(os.path.join(directory, name + ".json")) and not os.path.isfile(
        os.path.join(directory, name + ".err")
    ):
        return subprocess.CompletedProcess([], 0, json.dumps(_threads_response([])), "")
    return _respond(directory, name)


def _threads_response(resolved_flags):
    nodes = [{"isResolved": flag} for flag in resolved_flags]
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}


def respond(directory, args):
    if args[:2] == ["pr", "view"]:
        number = args[2]
        repo = args[args.index("--repo") + 1]
        fields = args[args.index("--json") + 1]
        prefix = "view_files" if "files" in fields.split(",") else "view"
        return _respond(directory, "{}_{}_{}".format(prefix, repo.replace("/", "-"), number))
    if args[:2] == ["pr", "ready"]:
        repo = args[args.index("--repo") + 1]
        with open(os.path.join(directory, "ready_calls.log"), "a") as log:
            log.write("{} {}\n".format(repo, args[2]))
        return _respond(directory, "ready_{}_{}".format(repo.replace("/", "-"), args[2]))
    if args[:2] == ["pr", "list"] and "--repo" in args:
        repo = args[args.index("--repo") + 1]
        return _respond(directory, "open_{}".format(repo.replace("/", "-")))
    if args[:2] == ["pr", "list"]:
        branch = args[args.index("--head") + 1]
        return _respond(directory, "list_{}".format(branch.replace("/", "-")))
    if args[:2] == ["api", "graphql"]:
        values = dict(arg.split("=", 1) for arg in args if "=" in arg and not arg.startswith("query="))
        return _respond_graphql(directory, "threads_{}-{}_{}".format(values["owner"], values["name"], values["number"]))
    if args[:1] == ["api"]:
        parts = args[1].split("/")
        repo = "-".join(parts[1:3])
        if parts[3] == "check-runs":
            return _respond(directory, "annotations_{}_{}".format(repo, parts[4]))
        branch = "-".join(parts[4:-1])
        return _respond(directory, "branch_checks_{}_{}".format(repo, branch))
    return subprocess.CompletedProcess([], 1, "", "fake gh: unhandled args {}".format(args))


def main():
    result = respond(os.environ["GUILD_TEST_GH_DIR"], sys.argv[1:])
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
