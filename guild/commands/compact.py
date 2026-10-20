from guild import compact, config, paths


def _resource_retention_days():
    return config.load_global(paths.global_config_path()).get("resource_retention_days")


def run(ctx, dry_run):
    with compact.lock(ctx) as acquired:
        if not acquired:
            return "compact already running"
        compact_plan = compact.plan(ctx, _resource_retention_days())
        if dry_run:
            return "\n".join(compact.report_lines(compact_plan, True))
        result = compact.apply(ctx, compact_plan)
    return "\n".join(compact.report_lines(compact_plan, False) + compact.result_lines(result))
