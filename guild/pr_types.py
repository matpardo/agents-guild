TYPES = ("feat", "fix", "hotfix", "chore", "refactor", "docs", "test", "perf", "ci", "build", "style")

_ALIASES = {
    "feature": "feat",
    "bugfix": "fix",
    "bug": "fix",
    "doc": "docs",
    "tests": "test",
}

_PREFIX_TYPES = dict({name: name for name in TYPES}, **_ALIASES)


def from_branch(branch):
    if not branch or "/" not in branch:
        return None
    return _PREFIX_TYPES.get(branch.split("/", 1)[0].lower())


def resolve(explicit, branch):
    if explicit is not None:
        return explicit
    return from_branch(branch)
