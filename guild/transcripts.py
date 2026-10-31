def find_transcript(projects_dir, session_id):
    if session_id is None:
        return None
    matches = sorted(projects_dir.glob("*/{}.jsonl".format(session_id)))
    if not matches:
        return None
    return matches[0]
