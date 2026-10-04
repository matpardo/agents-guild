def pr_url(repo, number):
    return "https://github.com/{}/pull/{}".format(repo, number)


def card_url(project_config, key):
    if key is None or project_config is None:
        return None
    tracker_config = project_config.get("tracker")
    if tracker_config is None:
        return None
    browse_url = tracker_config.get("browse_url")
    if browse_url is None:
        return None
    return browse_url + key
