class RunContext:
    def __init__(self, conn, session_id, cwd, now, origin, sessions_dir, projects_dir, state_dir):
        self.conn = conn
        self.session_id = session_id
        self.cwd = cwd
        self.now = now
        self.origin = origin
        self.sessions_dir = sessions_dir
        self.projects_dir = projects_dir
        self.state_dir = state_dir
