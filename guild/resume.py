import shlex

_RESUME_PROMPT = "Continue the work described in the guild handoff."


def _mode_flag(permission_mode):
    if permission_mode is None:
        return ""
    return " --permission-mode {}".format(shlex.quote(permission_mode))


def _generation_name(party, generation):
    return shlex.quote("{}-g{}".format(party, generation))


def _remote_control_flag(remote_control, party, generation):
    if not remote_control:
        return ""
    return " --remote-control {}".format(_generation_name(party, generation))


def resume_command(session_id, party, generation, permission_mode, remote_control):
    return "claude --resume {} --name {}{}{}".format(
        shlex.quote(session_id),
        _generation_name(party, generation),
        _mode_flag(permission_mode),
        _remote_control_flag(remote_control, party, generation),
    )


def fresh_command(party, next_generation, model, permission_mode, remote_control):
    model_flag = "" if model is None else " --model {}".format(shlex.quote(model))
    return "GUILD_RESUME={} claude -n {}{}{}{} {}".format(
        shlex.quote(party),
        _generation_name(party, next_generation),
        model_flag,
        _mode_flag(permission_mode),
        _remote_control_flag(remote_control, party, next_generation),
        shlex.quote(_RESUME_PROMPT),
    )


def tab_command(party, cwd, command):
    return "printf '\\033]0;%s\\007' {} && cd {} && {}".format(
        shlex.quote(party), shlex.quote(cwd), command
    )
