"""Built-in tools. Import this module to register them with the tool registry."""

import datetime
import uuid
from pathlib import Path

from fleetent import image_gen_client, vision_client
from fleetent.sandbox_client import SandboxClient
from fleetent.tool_registry import tool

# Generated images are written here, then a short reference is returned to the
# loop (never inline base64). Injectable module-level constant (no global mutable
# state): tests monkeypatch this to an isolated tmp path.
GENERATED_DIR: Path = Path("data/generated")

# Inbound images are written here, then a short reference (path) travels in the
# main context; analyze_image reads bytes back by reference. Injectable like
# GENERATED_DIR (no global mutable state) so tests isolate it to a tmp path.
UPLOADS_DIR: Path = Path("data/uploads")

# Map common image mimes to file extensions for stored uploads.
_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _save_image(data: bytes) -> str:
    """Write image bytes to GENERATED_DIR/{uuid4}.png and return a short reference.

    The reference is a path string (never base64), keeping the tool result and
    trace free of image payloads.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{uuid.uuid4().hex}.png"
    path.write_bytes(data)
    return str(path)


def _save_upload(data: bytes, mime: str) -> str:
    """Write inbound image bytes to UPLOADS_DIR/{uuid4}.{ext} and return a ref.

    The reference is a path string (never base64), keeping the main context and
    trace free of image payloads; analyze_image reads the bytes back via this
    same reference.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = _MIME_EXT.get(mime, ".bin")
    path = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    return str(path)


def _read_upload(ref: str) -> bytes:
    """Read image bytes back from an uploads reference (path)."""
    return Path(ref).read_bytes()


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
def read_skill(name: str) -> str:
    """Read a skill's full instructions by name (from the <available_skills> list).

    When a skill in the available_skills catalog matches the task, call this with
    its <name> to load the full SKILL.md, then follow it. Returns an error string
    if no skill with that name is registered, or a refusal if the skill failed the
    static injection audit (its content never reaches the model this way).
    """
    from fleetent import skill_registry

    entry = skill_registry._index.get(name)
    if entry is None:
        return f"error: no skill named {name!r}"
    if entry.audit_blocked:
        # Refuse before load(): a severe injection hit means the body must not
        # reach the model. load() itself still returns it for manual triage.
        return f"error: skill {name!r} was blocked by the static injection audit"
    return skill_registry.load(name)


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


@tool(risk_level="low")
async def generate_image(prompt: str, size: str = "") -> str:
    """Generate an image from a text prompt via the self-hosted images endpoint.

    Returns a short reference (file path) to the saved image, never inline base64.
    On endpoint failure/timeout, returns an explicit error result for the AI to
    handle rather than raising and breaking the loop.
    """
    try:
        data = await image_gen_client.generate(prompt, size=size or None)
    except image_gen_client.ImageGenError as exc:
        return f"error: image generation failed: {exc}"
    ref = _save_image(data)
    return f"image generated: {ref}"


@tool(risk_level="low")
async def analyze_image(ref: str, instruction: str) -> str:
    """Understand an image on demand via the self-hosted vision endpoint.

    `ref` is a stored-image reference (a path produced when an inbound image was
    saved); `instruction` is what to look for (e.g. "read the invoice total").
    Returns a structured text description, never inline base64. Use this to
    re-examine or compare images already in the conversation. On invalid ref,
    unconfigured endpoint, or endpoint failure, returns an explicit error result
    for the AI to handle rather than raising and breaking the loop.
    """
    try:
        data = _read_upload(ref)
    except OSError as exc:
        return f"error: cannot read image reference {ref!r}: {exc}"
    try:
        return await vision_client.analyze(data, instruction)
    except vision_client.VisionError as exc:
        return f"error: image analysis failed: {exc}"


@tool
def sub_agent(tasks: str) -> str:
    """Run multiple sub-tasks in parallel. tasks is a JSON array with 'name' and 'prompt' fields."""
    # Execution is intercepted by agent_loop before reaching here.
    return "sub_agent must be called through the agent loop"
