import shlex

_RESUME_PROMPT = "Continue the work described in the guild handoff."


def _mode_flag(permission_mode):
    if permission_mode is None:
        return ""
    return " --permission-mode {}".format(shlex.quote(permission_mode))


def resume_command(session_id, party, permission_mode):
    return "claude --resume {} --name {}{}".format(
        shlex.quote(session_id), shlex.quote(party), _mode_flag(permission_mode)
    )


def fresh_command(party, next_generation, model, permission_mode):
    model_flag = "" if model is None else " --model {}".format(shlex.quote(model))
    return "GUILD_RESUME={} claude -n {}-g{}{}{} {}".format(
        party, party, next_generation, model_flag, _mode_flag(permission_mode), shlex.quote(_RESUME_PROMPT)
    )


def tab_command(party, cwd, command):
    return "printf '\\033]0;%s\\007' {} && cd {} && {}".format(
        shlex.quote(party), shlex.quote(cwd), command
    )
