import shlex

RESUME_PROMPT = "Continue the work described in the guild brief."


def _mode_flag(permission_mode):
    if permission_mode is None:
        return ""
    return " --permission-mode {}".format(shlex.quote(permission_mode))


def _generation_name(party, generation):
    return shlex.quote("{}-g{}".format(party, generation))


def resume_command(session_id, party, generation, permission_mode):
    return "claude --resume {} --name {}{}".format(
        shlex.quote(session_id),
        _generation_name(party, generation),
        _mode_flag(permission_mode),
    )


def fresh_command(party, next_generation, model, permission_mode, prompt):
    model_flag = "" if model is None else " --model {}".format(shlex.quote(model))
    return "GUILD_RESUME={} claude -n {}{}{} {}".format(
        shlex.quote(party),
        _generation_name(party, next_generation),
        model_flag,
        _mode_flag(permission_mode),
        shlex.quote(prompt),
    )


def tab_command(party, cwd, command):
    return "printf '\\033]0;%s\\007' {} && cd {} && {}".format(
        shlex.quote(party), shlex.quote(cwd), command
    )
