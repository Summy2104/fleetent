import fnmatch


def check_tool_access(tool_name: str, allowed_tools: list[str]) -> bool:
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in allowed_tools)


def check_skill_access(
    skill_name: str,
    allowed_skills: list[str] | None,
    blocked_skills: list[str] | None,
) -> bool:
    """Decide whether a matched skill may be injected for the current agent.

    Mirrors `check_tool_access` for the skill dimension. opt-in posture:
    `allowed_skills is None` (agent did not declare a whitelist) denies every
    skill. A skill is injectable only when it matches the whitelist and is not
    excluded by the blocklist; `blocked_skills` None/[] means no exclusion.
    """
    if allowed_skills is None:
        return False
    if not check_tool_access(skill_name, allowed_skills):
        return False
    return not (blocked_skills and check_tool_access(skill_name, blocked_skills))
