class GuildError(Exception):
    def __init__(self, message, exit_code):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
