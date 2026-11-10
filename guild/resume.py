import shlex

RESUME_PROMPT = "Continue the work described in the guild brief."


CARRIED_PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk")


def _mode_flag(permission_mode):
    if permission_mode not in CARRIED_PERMISSION_MODES:
        return ""
    return " --permission-mode {}".format(shlex.quote(permission_mode))


def generation_name(party, generation):
    return "{}-g{}".format(party, generation)


def resume_command(session_id, party, generation, permission_mode):
    return "claude --resume {} --name {}{}".format(
        shlex.quote(session_id),
        shlex.quote(generation_name(party, generation)),
        _mode_flag(permission_mode),
    )


def fresh_command(party, next_generation, model, permission_mode, prompt):
    model_flag = "" if model is None else " --model {}".format(shlex.quote(model))
    return "GUILD_RESUME={} claude -n {}{}{} {}".format(
        shlex.quote(party),
        shlex.quote(generation_name(party, next_generation)),
        model_flag,
        _mode_flag(permission_mode),
        shlex.quote(prompt),
    )


def health_command(job_name, prompt, now):
    session_name = "health-{}-{}".format(job_name, now.astimezone().strftime("%Y%m%d-%H%M%S"))
    return "GUILD_ADVENTURER_JOB={} claude -n {} {}".format(
        shlex.quote(job_name), shlex.quote(session_name), shlex.quote(prompt)
    )


def tab_command(party, cwd, command):
    return "printf '\\033]0;%s\\007' {} && cd {} && {}".format(shlex.quote(party), shlex.quote(cwd), command)
