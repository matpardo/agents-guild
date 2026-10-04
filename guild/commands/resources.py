import time

from guild import probe
from guild.resources import collect

_DEADLINE_SECONDS = 20 * 60


def run_collect(ctx):
    return collect.collect(ctx, probe.run_capture, time.monotonic, _DEADLINE_SECONDS)
