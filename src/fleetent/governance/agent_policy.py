import fnmatch


def check_tool_access(tool_name: str, allowed_tools: list[str]) -> bool:
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in allowed_tools)
