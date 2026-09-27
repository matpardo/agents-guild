from guild import config, identity


def run(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    projects = config.load_all_projects(ctx.projects_dir)
    project = config.resolve_project(ctx.cwd, projects)
    session_label = ctx.session_id or "(none, human)"
    if binding is None:
        return "session: {}\nparty: (unbound)\nproject: {}".format(
            session_label, project or "(none)"
        )
    return "session: {}\nparty: {}\ngeneration: {}\nproject: {}".format(
        session_label, binding["party"], binding["generation"], project or binding["project"]
    )
