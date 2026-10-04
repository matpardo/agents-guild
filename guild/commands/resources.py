import time

from guild import probe
from guild.resources import collect, report

_DEADLINE_SECONDS = 20 * 60


def run_collect(ctx):
    return collect.collect(ctx, probe.run_capture, time.monotonic, _DEADLINE_SECONDS)


def run_report(ctx, project, since):
    model = report.build_model(ctx.conn, ctx.now, project, since, ctx.projects_dir)
    return report.render(model, ctx.now)
