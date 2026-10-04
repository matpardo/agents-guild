class FakeTmux:
    def __init__(self, installed, session_up, windows, create_returncode):
        self._installed = installed
        self.session_up = session_up
        self.windows = dict(windows)
        self.create_returncode = create_returncode
        self.raise_on_create = None
        self.calls = []

    def installed(self):
        return self._installed

    def run(self, args):
        self.calls.append(list(args))
        verb = args[0]
        if verb == "has-session":
            return (0 if self.session_up else 1), ""
        if verb == "list-windows":
            if not self.session_up:
                return 1, ""
            values = self.windows.keys() if "#{window_id}" in args else self.windows.values()
            return 0, "\n".join(values) + "\n"
        if verb in ("new-window", "new-session"):
            if self.raise_on_create is not None:
                raise self.raise_on_create
            if self.create_returncode != 0:
                return self.create_returncode, ""
            window_id = "@{}".format(len(self.windows) + 10)
            self.windows[window_id] = args[args.index("-n") + 1]
            self.session_up = True
            return 0, window_id + "\n"
        return 0, ""

    def launch_calls(self):
        return [call for call in self.calls if call[0] in ("new-window", "new-session")]

    def verbs(self):
        return [call[0] for call in self.calls]

