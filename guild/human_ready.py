from guild import timeutil


def _moment(text):
    return timeutil.from_iso(text.replace("Z", "+00:00"))


def _login(entry):
    return (entry.get("author") or {}).get("login")


def head_commit_date(commits, head_sha):
    for commit in commits:
        if commit.get("oid") == head_sha and commit.get("committedDate"):
            return commit["committedDate"]
    dates = [commit["committedDate"] for commit in commits if commit.get("committedDate")]
    return max(dates, key=_moment) if dates else None


def comments_after_head(head_date, author, comments, reviews):
    if head_date is None:
        return None
    head = _moment(head_date)
    stamped = [(entry, entry.get("createdAt")) for entry in comments]
    stamped += [(entry, entry.get("submittedAt")) for entry in reviews]
    return sum(
        1 for entry, stamp in stamped if stamp and (author is None or _login(entry) != author) and _moment(stamp) > head
    )


def ci_label_flag(project, labels):
    label = ((project or {}).get("human_ready") or {}).get("ci_label")
    if label is None:
        return None
    return int(any((entry.get("name") or "").casefold() == label.casefold() for entry in labels))
