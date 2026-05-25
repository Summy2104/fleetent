"""Built-in tools. Import this module to register them with the tool registry."""

import datetime

from fleetent.sandbox_client import SandboxClient
from fleetent.tool_registry import tool


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


@tool(risk_level="medium")
async def run_code(code: str) -> str:
    """Execute Python code in an isolated Docker container and return the output.

    The container has no network access and limited memory (256 MB).
    State does not persist between calls.
    """
    client = SandboxClient()
    ws_id = await client.create_workspace("run-code")
    try:
        result = await client.exec(ws_id, f"python3 -c {__import__('shlex').quote(code)}")
        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            parts.append(f"[stderr] {result.stderr.rstrip()}")
        if result.exit_code != 0:
            parts.append(f"[exit {result.exit_code}]")
        return "\n".join(parts) if parts else "(no output)"
    finally:
        await client.destroy_workspace(ws_id)


@tool(risk_level="high")
def schedule_task(name: str, cron_expr: str, message: str, timezone: str = "UTC", user_id: str = "default") -> str:
    """Create a recurring cron task that runs the agent with the given message.
    cron_expr is a standard 5-field expression e.g. '0 9 * * 1-5'."""
    from fleetent import schedule_store, cron_scheduler
    task = schedule_store.create(
        name=name,
        cron_expr=cron_expr,
        timezone=timezone,
        user_id=user_id,
        agent_name=None,
        message=message,
        source="tool",
    )
    return f"Scheduled task created: id={task['id']!r} name={name!r} cron={cron_expr!r}"


@tool(risk_level="medium")
def cancel_task(task_id: str) -> str:
    """Cancel a scheduled cron task by its id."""
    from fleetent import schedule_store
    deleted = schedule_store.delete(task_id)
    if not deleted:
        return f"error: task {task_id!r} not found"
    return f"Scheduled task {task_id!r} removed"


@tool
def sub_agent(tasks: str) -> str:
    """Run multiple sub-tasks in parallel. tasks is a JSON array with 'name' and 'prompt' fields."""
    # Execution is intercepted by agent_loop before reaching here.
    return "sub_agent must be called through the agent loop"
