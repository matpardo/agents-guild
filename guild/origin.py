import getpass
import os
import socket


def current_origin():
    override = os.environ.get("GUILD_ORIGIN")
    if override:
        return override
    return "{}@{}".format(getpass.getuser(), socket.gethostname())
