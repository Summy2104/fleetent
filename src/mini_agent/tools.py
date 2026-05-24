"""Built-in tools. Import this module to register them with the tool registry."""

import datetime

from mini_agent.tool_registry import tool


@tool
def get_current_time() -> str:
    """Return the current UTC time as a string."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression and return the result."""
    allowed = set("0123456789+-*/()., ")
    if not all(c in allowed for c in expression):
        return "error: only arithmetic expressions are allowed"
    try:
        result = eval(expression)  # noqa: S307  # whitelist-validated above
        return str(result)
    except Exception as exc:
        return f"error: {exc}"


@tool
def read_file(path: str) -> str:
    """Read a local file and return its contents (first 2000 chars)."""
    try:
        with open(path) as f:
            return f.read(2000)
    except OSError as exc:
        return f"error: {exc}"


@tool(risk_level="medium")
def write_file(path: str, content: str) -> str:
    """Write content to a local file. Requires approval before executing."""
    try:
        with open(path, "w") as f:
            f.write(content)
        return f"written {len(content)} bytes to {path}"
    except OSError as exc:
        return f"error: {exc}"


@tool
def sub_agent(tasks: str) -> str:
    """Run multiple sub-tasks in parallel. tasks is a JSON array with 'name' and 'prompt' fields."""
    # Execution is intercepted by agent_loop before reaching here.
    return "sub_agent must be called through the agent loop"
