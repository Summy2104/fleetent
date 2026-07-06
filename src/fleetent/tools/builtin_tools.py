"""Built-in tools. Import this module to register them with the tool registry."""

import asyncio
import datetime
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

if TYPE_CHECKING:
    from fleetent.integrations.sandbox.manager import WorkspaceScope

from fleetent import eval_logger, memory
from fleetent.integrations.sandbox import (
    BaseSandboxBackend,
    ExecResult,
    SandboxManager,
    build_sandbox_env,
    cap_or_spill,
    redact_secrets,
)
from fleetent.integrations.sandbox import output_truncation as sot
from fleetent.runtime.cancellation import CancelToken
from fleetent.runtime.error_classifier import (
    CLASSIFICATION_TABLE,
    ErrorCategory,
    ErrorClassification,
)
from fleetent.tools import image_gen_client, vision_client
from fleetent.tools.registry import ToolContext, tool

logger = logging.getLogger(__name__)

# How often the cancel watcher polls the token while exec runs (seconds). Small
# enough that cancellation is observed promptly, large enough to stay cheap.
_CANCEL_POLL_INTERVAL = 0.05

# Returned (not raised) when a sandbox exec exceeds its exec_timeout deadline (SB7),
# so the conversation can continue. Distinct from the external-cancel text.
_SANDBOX_TIMEOUT_TEXT = "沙箱执行超时：代码执行超过沙箱时限，容器已被强制终止。"


def _sandbox_timeout_classification() -> ErrorClassification:
    """Read AR5's sandbox_timeout classification directly (SB7 D3).

    The timeout→category decision is the sandbox's own domain knowledge; we then
    consume AR5's read-only flags straight from CLASSIFICATION_TABLE rather than
    calling classify() (which only recognizes APIStatusError).
    """
    return CLASSIFICATION_TABLE[ErrorCategory.sandbox_timeout]


# Process-wide sandbox lifecycle manager (SB2). Lazily built on first run_code so
# config is read once, not per call; injectable (tests monkeypatch this to an
# isolated instance) rather than a hidden global — the registry lives on the
# instance, not at module scope.
_MANAGER: SandboxManager | None = None


def _get_manager() -> SandboxManager:
    global _MANAGER
    if _MANAGER is None:
        from fleetent.integrations.sandbox.factory import create_backend

        _MANAGER = SandboxManager(backend=create_backend())
    return _MANAGER


def init_sandbox_manager(
    agent: object | None = None,
    *,
    agent_skills_root: str | Path | None = None,
) -> SandboxManager:
    """(Re)build the process sandbox manager with the agent-selected backend.

    Called by the agent runtime at startup so a standalone agent's `agent.yaml`
    `sandbox.backend` override takes effect (factory precedence: agent > platform >
    docker). `agent` is an `AgentFile`; typed loosely to avoid a runtime import cycle.

    `agent_skills_root` (sandbox-skill-mount-per-agent-root) is the per-agent skills
    root that boot also scans the skill index from (`home_dir/skills`). When the agent
    leaves `sandbox.skill_mount.source` unset, this becomes the mount source default so
    the container's `/workspace/skills` == the scan root, rather than the global
    `<base>/skills` the manager would otherwise fall back to. An explicit
    `skill_mount.source` still wins; None (no boot wiring) preserves the global fallback.
    """
    global _MANAGER
    from fleetent.agent_config import AgentFile
    from fleetent.integrations.sandbox import SkillMountConfig
    from fleetent.integrations.sandbox.config import (
        SandboxResources,
        resources_from_agent_settings,
    )
    from fleetent.integrations.sandbox.factory import create_backend
    from fleetent.integrations.sandbox.manager import WorkspaceScope

    resolved = agent if isinstance(agent, AgentFile) else None
    skill_mount = None
    image_persistence = False
    setup_command: str | None = None
    # Per-agent sandbox resource/hardening profile + lifecycle (per-agent-sandbox-resources).
    # Built from the agent's `sandbox.resources` over code defaults; no platform.yaml.
    # `workspace_scope` collapses to one resource tier (SESSION == AGENT).
    resources = SandboxResources()
    scope = WorkspaceScope.SESSION
    idle_hours = 2.0
    # Multi-user run-shape signal (sandbox-multi-user-default). Fail-safe: default True
    # even with no AgentFile, so the manager's guard correcting a configured `agent`
    # workspace_scope to `session` is always live (a single-process one-shot is session
    # regardless, so this is harmless there). A configured AgentFile carries its own
    # `sandbox.multi_user` (itself defaulting True; explicit false opts a single-user
    # deployment out). Carried via config to keep the runtime free of platform knowledge.
    multi_user = True
    if resolved is not None:
        # Per-agent override of the skills bind-mount (sandbox-skill-mount); None lets
        # the manager fall back to the platform `sandbox.skill_mount` defaults — except
        # boot supplies the per-agent skills root so an unset source defaults to the same
        # root the skill index was scanned from (sandbox-skill-mount-per-agent-root).
        sm = resolved.sandbox.skill_mount
        source = sm.source
        if source is None and agent_skills_root is not None:
            source = str(agent_skills_root)
        skill_mount = SkillMountConfig(enabled=sm.enabled, read_only=sm.read_only, source=source)
        # Per-agent dependency-image persistence (sandbox-image-persistence): an
        # independent switch from workspace_scope. Default off keeps prior behaviour.
        image_persistence = resolved.sandbox.image_persistence
        setup_command = resolved.sandbox.setup_command
        multi_user = resolved.sandbox.multi_user
        resources = resources_from_agent_settings(resolved.sandbox.resources)
        scope = _coerce_workspace_scope(resolved.sandbox.workspace_scope)
        if resolved.sandbox.idle_hours is not None and resolved.sandbox.idle_hours > 0:
            idle_hours = resolved.sandbox.idle_hours
    _MANAGER = SandboxManager(
        backend=create_backend(resolved),
        skill_mount=skill_mount,
        # Collapsed single resource tier — one per-agent profile for both scopes.
        resources_by_scope={WorkspaceScope.SESSION: resources, WorkspaceScope.AGENT: resources},
        scope=scope,
        idle_hours=idle_hours,
        image_persistence=image_persistence,
        setup_command=setup_command,
        multi_user=multi_user,
    )
    return _MANAGER


def _coerce_workspace_scope(value: str | None) -> "WorkspaceScope":
    """Map a per-agent `sandbox.workspace_scope` string to WorkspaceScope; invalid → SESSION."""
    from fleetent.integrations.sandbox.manager import WorkspaceScope

    if value is None:
        return WorkspaceScope.SESSION
    try:
        return WorkspaceScope(value)
    except ValueError:
        return WorkspaceScope.SESSION


# Workspace-relative subdirectories for image products (sandbox-workspace-root).
# Both live under the per-scope `/workspace` (= host workspace dir), so the model
# sees a single root and references flow as workspace-relative paths that resolve to
# the same physical file in container and host-degrade modes.
_GENERATED_SUBDIR = "generated"
_UPLOADS_SUBDIR = "uploads"

# Map common image mimes to file extensions for stored uploads.
_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _workspace_root_for(tool_context: ToolContext | None) -> Path:
    """Resolve the per-scope host workspace dir for the current tool context (D6).

    Reuses the manager's single `workspace_host_path` resolution point so generated/
    uploaded products land in the very directory `run_code` / file tools are fenced
    to (container `/workspace` = this host dir). Degrades to the run_code default key
    when called without a context, mirroring run_code's own fallback so the workspace
    key matches.
    """
    manager = _get_manager()
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = tool_context.agent_name if tool_context is not None else None
    return manager.workspace_host_path(manager.scope, session_id, agent_name or "default")


def _workspace_scope_and_root(tool_context: ToolContext | None) -> tuple[object, Path]:
    """Return ``(manager.scope, host workspace dir)`` for the current tool context.

    Used by send_file to gate on workspace scope while reusing the same single
    `workspace_host_path` resolution point (so the resolved dir is exactly the one
    run_code / file tools are fenced to). Kept out of the tool body so the
    sole-sandbox-consumer guard (run_code only) is not tripped by send_file.
    """
    manager = _get_manager()
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = (tool_context.agent_name if tool_context is not None else None) or "default"
    return manager.scope, manager.workspace_host_path(manager.scope, session_id, agent_name)


def _save_image(data: bytes, tool_context: ToolContext | None = None) -> str:
    """Write image bytes to the per-scope workspace `generated/` and return a relative ref.

    The reference is the workspace-relative `generated/<uuid>.png` (never base64, never
    a host-absolute path), so the model stays in the single `/workspace` world and the
    file is readable via file tools / run_code by the same relative path.
    """
    root = _workspace_root_for(tool_context)
    generated = root / _GENERATED_SUBDIR
    generated.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    (generated / name).write_bytes(data)
    return f"{_GENERATED_SUBDIR}/{name}"


def _save_upload(data: bytes, mime: str, tool_context: ToolContext | None = None) -> str:
    """Write inbound image bytes to the per-scope workspace `uploads/`, return a relative ref.

    Aligns with `normalizer._save_file_to_workspace`: the reference is the
    workspace-relative `uploads/<uuid>.<ext>` (never base64, never host-absolute), and
    analyze_image reads the bytes back via this same relative reference.
    """
    root = _workspace_root_for(tool_context)
    uploads = root / _UPLOADS_SUBDIR
    uploads.mkdir(parents=True, exist_ok=True)
    ext = _MIME_EXT.get(mime, ".bin")
    name = f"{uuid.uuid4().hex}{ext}"
    (uploads / name).write_bytes(data)
    return f"{_UPLOADS_SUBDIR}/{name}"


def _read_upload(ref: str, tool_context: ToolContext | None = None) -> bytes:
    """Read image bytes from an uploads reference, via workspace resolution (D6).

    A workspace-relative ref (`uploads/<name>.png`) resolves under the per-scope host
    workspace dir (= container `/workspace`, same physical file in both modes). A
    legacy host-absolute ref (from a pre-migration session) is read directly as a
    backward-compatibility fallback so historical references keep working.
    """
    if os.path.isabs(ref):
        return Path(ref).read_bytes()
    root = _workspace_root_for(tool_context)
    return (root / ref).read_bytes()


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
def whoami(tool_context: ToolContext | None = None) -> str:
    """Return the current requester's identity and conversation context.

    Use when you need to know who is talking to you (platform user id + name),
    where (DM vs which channel), or the current time. Reads the inbound message's
    session context; returns "未知" fields when unavailable (e.g. a CLI run with no
    IM context). Never raises.
    """
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    if sc is None:
        return f"发起人: 未知 (无 IM 上下文)\n当前时间: {now}"

    def _g(attr: str) -> str:
        return str(getattr(sc, attr, "") or "未知")

    scene = "私信 (DM)" if _g("chat_type") == "dm" else f"频道 {_g('channel_name')}"
    return (
        f"平台: {_g('platform')}\n"
        f"发起人 ID: {_g('sender_id')}\n"
        f"发起人名称: {_g('sender_name')}\n"
        f"场景: {scene}\n"
        f"当前时间: {now}"
    )


@tool
def tool_search(query: str, limit: int = 10, tool_context: ToolContext | None = None) -> str:
    """Look up tools that are listed in the catalog but not yet callable, and load them.

    Many tools (especially MCP server tools) appear in the deferred-tools catalog as a
    name + one-line description but are NOT yet in your callable tool set. Use this to
    fetch their full schemas. Pass a keyword query (e.g. "create jira issue") to get the
    best matches, or "select:name1,name2" to fetch specific tools by exact name. Loaded
    tools become callable from your NEXT turn onward (this turn only returns their
    schemas). Never raises.
    """
    pool = getattr(tool_context, "deferred_pool", None) or {}
    if not pool:
        return "没有可检索的延迟加载工具：当前所有工具均已直接可用。"

    from fleetent.tools import deferred

    names = deferred.search_deferred(query, pool, limit=limit)
    if tool_context is not None and names:
        tool_context.activated_tools.update(names)

    lines: list[str] = []
    if names:
        lines.append(f"已加载 {len(names)} 个工具，下一轮起可调用：")
        lines.append(json.dumps([pool[n] for n in names], ensure_ascii=False, indent=2))
    else:
        lines.append(f"未匹配到工具：{query!r}。请换关键词，或查看 deferred-tools 目录。")

    if query.startswith("select:"):
        wanted = [n.strip() for n in query[len("select:") :].split(",") if n.strip()]
        missing = [n for n in wanted if n not in pool]
        if missing:
            lines.append("未找到（不存在或无权限）：" + ", ".join(missing))
    return "\n".join(lines)


@tool
async def recall_memory(subject: str | None = None, tool_context: ToolContext | None = None) -> str:
    """List the stored long-term memories about the current user, in full.

    Use when the user asks to see what you remember — "列出我的所有记忆", "你记得
    我什么", or "你记得张三什么" (pass that person's name as ``subject``). Unlike
    the relevant memories auto-injected each turn, this returns EVERYTHING stored
    for the current user (no relevance ranking, no truncation), grouped by who
    each fact is about. Leave ``subject`` empty for all; set it to filter to one
    person (e.g. the user, the assistant, or a named contact). Never raises.

    Note: memories are extracted automatically after each conversation turn — there
    is no separate "save memory" tool. When a user shares new information, just
    acknowledge it naturally; the pipeline will persist it.
    """
    principal = getattr(tool_context, "principal", None) if tool_context else None
    user_id = getattr(principal, "user_id", None) if principal else None
    if not user_id:
        return "无法确定当前用户身份，暂时无法列出记忆。"
    try:
        facts = memory.list_active_facts(user_id, subject=subject)
    except Exception as exc:  # noqa: BLE001 — recall must never break the turn
        return f"读取记忆时出错：{exc}"
    if not facts:
        scope = f"关于「{subject}」的" if subject else ""
        return f"目前没有{scope}记忆。"

    grouped: dict[str, list[str]] = {}
    for fact in facts:
        line = fact.statement or f"{fact.subject} {fact.relation}: {fact.object}"
        grouped.setdefault(fact.subject, []).append(line)
    sections = []
    for subj, lines in grouped.items():
        body = "\n".join(f"- {line}" for line in lines)
        sections.append(f"【{subj}】\n{body}")
    return "\n\n".join(sections)


@tool(connector="github", scopes=["repo"])
def github_connection_status(*, client: dict[str, Any]) -> str:
    """Return a safe summary proving the per-user GitHub credential is wired."""
    scopes = client.get("scope") or client.get("scopes") or []
    if isinstance(scopes, list):
        scope_summary = ",".join(str(scope) for scope in scopes) if scopes else "none"
    else:
        scope_summary = str(scopes)
    return f"github credential ready; scopes={scope_summary}"


@tool
def set_mcp_credential(server_id: str, key: str, tool_context: ToolContext | None = None) -> str:
    """Provide YOUR OWN api-key/bearer for a per-user MCP server (private DM only).

    Use this only when a per-user api-key MCP server tells you it needs your credential AND
    that server allows in-conversation submission. Pass the server id and your key. For your
    security this is accepted ONLY in a private direct message (never a shared channel) — in
    a channel, or when the server prefers its secure form, use the form link instead. The key
    is stored encrypted, isolated to you, and is never shown back in the conversation. Most
    servers default to the secure form and will reject this tool.
    """
    from fleetent.integrations.mcp import per_user_tokens
    from fleetent.integrations.mcp.client import find_registered_server

    server = find_registered_server(server_id)
    if server is None or getattr(server, "auth_type", None) != "api_key_per_user":
        return f"error: '{server_id}' is not a per-user api-key server"
    if getattr(server, "credential_input", "form") not in ("tool", "both"):
        return (
            f"error: '{server_id}' only accepts your key via its secure form link "
            f"(this tool is disabled for it)"
        )
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    if getattr(sc, "chat_type", None) != "dm":
        return (
            "error: for your security, provide your key in a private DM (or use the secure "
            "form link) — never in a shared channel"
        )
    principal = getattr(tool_context, "principal", None) if tool_context else None
    user_id = getattr(principal, "user_id", None) if principal else None
    if not user_id:
        return "error: cannot determine your identity; unable to store the credential"
    agent_id = getattr(tool_context, "agent_name", None) if tool_context else None
    if not per_user_tokens.store_user_credential(server_id, user_id, agent_id, key):
        return f"error: failed to store your credential for '{server_id}'"
    return f"Your credential for '{server_id}' was saved securely. Try your request again."


@tool
def read_skill(
    name: str,
    file_path: str | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Read a skill's full instructions by name (from the <available_skills> list).

    When a skill in the available_skills catalog matches the task, call this with
    its <name> to load the full SKILL.md, then follow it. Pass `file_path` (a path
    relative to the skill directory, e.g. ``references/api.md``) to instead read one
    of the skill's supporting files; the path is confined to the skill directory.
    Returns an error string if no skill with that name is registered, or a refusal
    if the skill failed the static injection audit (its content never reaches the
    model this way).
    """
    from fleetent.skills import registry as skill_registry

    entry = skill_registry._index.get(name)
    if entry is None:
        return f"error: no skill named {name!r}"
    # skill-user-access: a restricted skill the requester may not access is refused with
    # the SAME text as a genuinely-missing skill — never disclose its existence. Gated
    # before audit/load so it covers both the by-name and file_path paths.
    if not _skill_visible_to_requester(name, tool_context):
        return f"error: no skill named {name!r}"
    if entry.audit_blocked:
        # Refuse before load(): a severe injection hit means the body must not
        # reach the model. load() itself still returns it for manual triage. The
        # same gate applies to supporting files so no part of a blocked skill leaks.
        _audit_skill_refusal(name, tool_context)
        return f"error: skill {name!r} was blocked by the static injection audit"
    if file_path is not None:
        out = skill_registry.read_skill_file(name, file_path)
        _record_skill_hit(name, tool_context)
        return out
    body = skill_registry.load(name)
    _record_skill_hit(name, tool_context)
    # Append the fixed exec-face / $SKILLS_DIR guidance so the model runs the skill's
    # scripts via run_code under the single /workspace world (skill-read-on-demand).
    return body + skill_registry._READ_SKILL_GUIDANCE


def _skill_view_source(tool_context: ToolContext | None) -> str | None:
    """Build this session's filtered skills view and return its path (skill-user-access).

    When the agent declares `skill_user_access`, the sandbox must mount only the skills
    this session's user may use — restricted skills the user can't access are physically
    absent so `run_code`/`read_file` can't reach them. Computes the allowed skill names
    (every indexed skill that passes `skill_visible_to_user` for this requester) and
    builds the `.views/<scope_key>/` hardlink view. Returns None when no access map is
    configured (then the caller mounts the full root, unchanged behavior).
    """
    access_map = getattr(tool_context, "skill_user_access", None)
    if not access_map:
        return None
    from fleetent.skills import registry as skill_registry

    principal = getattr(tool_context, "principal", None)
    session_context = getattr(tool_context, "session_context", None)
    return skill_registry.session_skill_view_for(
        getattr(tool_context, "scope_key", None) or "default",
        user_id=getattr(principal, "user_id", None),
        chat_type=getattr(session_context, "chat_type", None),
        access_map=access_map,
        rebuild=False,
    )


def _skill_visible_to_requester(name: str, tool_context: ToolContext | None) -> bool:
    """Whether the read_skill requester may access this skill (skill-user-access).

    Resolves the requester user_id (from the principal) + chat_type (from the inbound
    session context) and the active agent's `skill_user_access`, all carried on the
    tool_context, and delegates to the registry's single visibility predicate. No
    context (e.g. CLI direct call) → no access map → visible (unchanged).
    """
    from fleetent.skills import registry as skill_registry

    access_map = getattr(tool_context, "skill_user_access", None)
    if not access_map:
        return True
    principal = getattr(tool_context, "principal", None)
    user_id = getattr(principal, "user_id", None)
    session_context = getattr(tool_context, "session_context", None)
    chat_type = getattr(session_context, "chat_type", None)
    return skill_registry.skill_visible_to_user(
        name, user_id=user_id, chat_type=chat_type, access_map=access_map
    )


@tool
def list_skills(keyword: str | None = None, category: str | None = None) -> str:
    """List available skills (name + description) as JSON, optionally filtered.

    The on-demand query for the skill catalog: use it when the always-injected
    <available_skills> list is truncated, or to narrow by topic. `keyword` matches
    (case-insensitive) a skill's name, description, or tags; `category` matches a
    tag. Both omitted lists every available skill. Returns only names and
    descriptions — call `read_skill` with a name to load a skill's full content.
    """
    from fleetent.skills import registry as skill_registry

    return json.dumps(skill_registry.query_skills(keyword=keyword, category=category))


@tool(risk_level="medium")
def skill_manage(
    action: Literal["create", "patch", "edit", "delete", "write_file", "remove_file"],
    name: str,
    content: str | None = None,
    file_path: str | None = None,
    file_content: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    replace_all: bool = False,
    tool_context: ToolContext | None = None,
) -> str:
    """Create, edit, or delete a skill in this agent's own skill library.

    User-driven authoring of the agent's skills. Every action is a write and is
    routed through the approval gate, so it takes effect only after a human approves.
    Actions: `create` (new skill from `content` = full SKILL.md), `edit` (rewrite
    SKILL.md with `content`), `patch` (replace `old_string` with `new_string` in
    SKILL.md, or in `file_path` when given; `replace_all` for every occurrence),
    `delete` (remove the skill), `write_file` (write `file_content` to `file_path`),
    `remove_file` (delete `file_path`). Writes are confined to this agent's skills;
    builtin skills are read-only. Returns an `ok:`/`error:` result string.
    """
    from fleetent.skills import registry as skill_registry

    try:
        if action == "create":
            created_at = datetime.datetime.now(datetime.UTC).isoformat()
            skill_registry.create_skill(name, content or "", created_at=created_at)
        elif action == "edit":
            skill_registry.edit_skill(name, content or "")
        elif action == "patch":
            skill_registry.patch_skill(
                name,
                old_string or "",
                new_string or "",
                file_path=file_path,
                replace_all=replace_all,
            )
        elif action == "delete":
            skill_registry.delete_skill(name)
        elif action == "write_file":
            skill_registry.write_skill_file(name, file_path or "", file_content or "")
        elif action == "remove_file":
            skill_registry.remove_skill_file(name, file_path or "")
        else:
            return f"error: unknown action {action!r}"
    except (ValueError, OSError) as exc:
        return f"error: {exc}"
    _record_skill_authored(action, name, tool_context)
    return f"ok: skill_manage {action} for skill {name!r} succeeded"


def _record_skill_authored(action: str, name: str, tool_context: ToolContext | None) -> None:
    """Record a successful skill_manage write as an agent-side observability trace.

    Best-effort and agent-side only (never a platform store, per agent/platform
    decoupling): a recording failure is logged and swallowed so it never changes the
    write outcome. The platform reads authoring activity from this trace.
    """
    from fleetent.observability.traces import TraceEvent, record_trace_event

    session_id = tool_context.session_id if tool_context else None
    try:
        record_trace_event(
            TraceEvent(
                run_id=session_id or "",
                event_type="skill_authored",
                payload={"skill_name": name, "action": action},
                session_id=session_id,
                agent_name=tool_context.agent_name if tool_context else None,
            )
        )
    except Exception as exc:  # noqa: BLE001 — observability is a side channel; never block
        logger.warning("skill_authored_record_failed", extra={"skill": name, "error": str(exc)})


def _record_skill_hit(name: str, tool_context: ToolContext | None) -> None:
    """Record a successful read_skill load as an agent-side observability trace event.

    Best-effort: a recording failure (DB unavailable, etc.) is logged and swallowed so it
    never blocks returning the skill body. Writes to the agent's observability trace —
    never to a platform store (agent/platform decoupling); the platform reads per-skill
    metrics from the trace.
    """
    from fleetent.observability.traces import TraceEvent, record_trace_event

    agent_name = tool_context.agent_name if tool_context else None
    session_id = tool_context.session_id if tool_context else None
    try:
        record_trace_event(
            TraceEvent(
                run_id=session_id or "",
                event_type="skill_hit",
                payload={"skill_name": name},
                session_id=session_id,
                agent_name=agent_name,
            )
        )
    except Exception as exc:  # noqa: BLE001 — observability is a side channel; never block
        logger.warning("skill_hit_record_failed", extra={"skill": name, "error": str(exc)})


def _audit_skill_refusal(name: str, tool_context: ToolContext | None) -> None:
    """Record a read_skill refusal of an audit_blocked skill (skill-read-refusal-audit).

    Best-effort: the refusal is the security guarantee; a failure of this side-channel
    audit write must never change the refusal outcome (logged, then swallowed).
    """
    from fleetent import audit_log

    detail = {
        "reason": "audit_blocked",
        "session_id": tool_context.session_id if tool_context else None,
        "agent_name": tool_context.agent_name if tool_context else None,
    }
    try:
        audit_log.write_audit(None, "skill.read_refused", "skill", name, detail=detail)
    except Exception as exc:  # noqa: BLE001 — audit is a side channel; never block the refusal
        logger.warning("skill_read_refusal_audit_failed", extra={"skill": name, "error": str(exc)})


# read_file and write_file have moved to file_tools.py.
# Re-exported here so existing imports remain unbroken.
from fleetent.tools.file_tools import read_file as read_file  # noqa: F401,E402
from fleetent.tools.file_tools import write_file as write_file  # noqa: F401,E402


async def _exec_or_cancel(
    client: BaseSandboxBackend,
    ws_id: str,
    command: str,
    cancel_token: CancelToken,
    session_id: str | None = None,
) -> ExecResult | None:
    """Run exec, aborting if the token cancels or its deadline passes.

    Returns the ExecResult on normal completion, or None when cancellation (or a
    passed deadline) is observed first — in which case the container is terminated
    gracefully (SB7: SIGTERM → grace → SIGKILL) and then removed, rather than left
    hanging on a blocked exec. The caller distinguishes timeout from external
    cancel by whether the token's own deadline has passed. `session_id` enables
    session-snapshot continuity (cwd defaults to the mounted /workspace).
    """
    exec_task = asyncio.create_task(client.exec(ws_id, command, session_id=session_id))
    while True:
        if cancel_token.is_cancelled():
            exec_task.cancel()
            await asyncio.gather(exec_task, return_exceptions=True)
            # SB7: terminate the container process gracefully (SIGTERM → SIGKILL)
            # rather than the violent rm -f, then remove it (idempotent) so the
            # registry forget below cannot collide with a lingering stopped name.
            await client.kill_workspace(ws_id)
            await client.destroy_workspace(ws_id)
            return None
        done, _ = await asyncio.wait({exec_task}, timeout=_CANCEL_POLL_INTERVAL)
        if exec_task in done:
            return exec_task.result()


# /exchange/<server_id>/<rel> references embedded in run_code source (staging fallback).
_EXCHANGE_REF_RE = re.compile(r"/exchange/[A-Za-z0-9_.-]+/[^\s\"'<>),;]+")


async def _stage_exchange_refs(
    code: str, scope_key: str | None, backend: BaseSandboxBackend, ws_id: str
) -> int:
    """Stage attribution-passing /exchange refs into the container (D5 degrade, §4.7/4.8).

    No-op on `exchange_mount`-capable backends (the ro view mount handles it). Otherwise the
    `/exchange/...` paths literally referenced in the code are resolved through
    artifact_exchange (own-scope only; cross-scope / unregistered are silently skipped — not
    staged) and copied into the container before exec. Returns the count staged; logs a
    degrade line when refs were present. Best-effort: a copy failure is logged, never raised.
    """
    if getattr(backend.capabilities, "exchange_mount", False):
        return 0
    refs = sorted(set(_EXCHANGE_REF_RE.findall(code)))
    if not refs:
        return 0
    from fleetent import artifact_exchange

    staged = 0
    for ref in refs:
        try:
            host = artifact_exchange.resolve(ref, scope_key, approved=False)
        except Exception:  # noqa: BLE001 — cross-scope/unregistered/gone → not staged
            continue
        try:
            await backend.stage_file(ws_id, ref, host.read_bytes())
            staged += 1
        except Exception as exc:  # noqa: BLE001 — staging is best-effort, never break exec
            logger.warning("exchange_staging_copy_failed ref=%s error=%s", ref, exc)
    logger.warning(
        "exchange_staging_degrade backend=%s refs=%d staged=%d",
        getattr(backend, "name", "?"),
        len(refs),
        staged,
    )
    return staged


@tool(risk_level="medium", self_truncates=True)
async def run_code(
    code: str,
    cancel_token: CancelToken | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Execute Python code in an isolated Docker container and return the output.

    The container has no network access and limited memory (256 MB).
    State does not persist between calls.
    """
    token = cancel_token if cancel_token is not None else CancelToken()
    manager = _get_manager()
    # SB3 D5: key the workspace on the context's session id so SB2 can locate/reuse
    # it; degrade to the default key when called without a context (direct/unbound
    # call) — never raise here. agent_name feeds agent-scope naming.
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = tool_context.agent_name if tool_context is not None else None
    scope = manager.scope
    # SB5 D4: the only injection source is the agent's predeclared
    # `features.sandbox_env`; build_sandbox_env filters sensitive names (and host
    # env is not passed). runtime_env is left unwired — no AI/user-supplied env.
    features = tool_context.features if tool_context is not None else {}
    agent_env = features.get("sandbox_env")
    env = build_sandbox_env(agent_env=agent_env)
    ws_id = await manager.acquire(
        scope,
        session_id,
        agent_name or "default",
        env=env,
        skill_mount_source=_skill_view_source(tool_context),
    )
    # unified-file-exchange §4.7/4.8: on a backend without exchange_mount, stage the code's
    # attribution-passing /exchange refs into the container before exec (no-op on capable
    # backends, where the ro view mount already exposes them). Best-effort, never breaks run.
    try:
        scope_key = getattr(tool_context, "scope_key", None)
        await _stage_exchange_refs(code, scope_key, manager.backend, ws_id)
    except Exception as exc:  # noqa: BLE001 — staging is auxiliary, never break run_code
        logger.warning("exchange_staging_failed error=%s", exc)
    command = f"python3 -c {__import__('shlex').quote(code)}"
    # SB2 D4: normal completion does NOT destroy — reuse is the point; destruction
    # is owned by release_session / sweep_idle. AR19's cancel path still hard-aborts
    # by destroying the container; we then drop the registry entry so a later acquire
    # rebuilds (find_workspace miss) rather than handing back a destroyed container.
    # SB9 D4: time only the exec (not container acquisition); container-lifecycle
    # timing is SB2's concern. exit_code / byte sizes come from the ExecResult.
    # SB7: merge the sandbox exec_timeout deadline with the external token via the
    # AR20 `parent` link, so a single token reflects "own timeout OR external/parent
    # cancel". On trigger we tell the two apart by whether this child's own deadline
    # has passed (timeout) or not (external cancel) — mirrors AR20's timed_out vs
    # cancelled split.
    exec_timeout = manager.resources_for(scope).exec_timeout
    start = time.monotonic()
    child = CancelToken(deadline=start + exec_timeout, parent=token)
    result = await _exec_or_cancel(manager.backend, ws_id, command, child, session_id=session_id)
    if result is not None and manager.backend.is_workspace_missing(result):
        # Container died between acquire and exec (sandbox-liveness-reacquire):
        # drop the stale registration, rebuild on the same host-mounted workspace,
        # retry exactly once instead of surfacing an infrastructure error.
        manager.invalidate(scope, session_id, agent_name or "default")
        ws_id = await manager.acquire(
            scope,
            session_id,
            agent_name or "default",
            env=env,
            skill_mount_source=_skill_view_source(tool_context),
        )
        result = await _exec_or_cancel(
            manager.backend, ws_id, command, child, session_id=session_id
        )
    elapsed = time.monotonic() - start
    if result is None:
        manager.forget(manager.container_name(scope, session_id, agent_name or "default"))
        # Cancelled/timed-out exec yields no ExecResult; skip the trace rather than
        # log placeholder metadata. Distinguish sandbox timeout from external cancel.
        if child.deadline is not None and time.monotonic() >= child.deadline:
            classification = _sandbox_timeout_classification()  # AR5 sandbox_timeout (D3)
            logger.warning(
                "sandbox_exec_timeout container=%s category=%s should_retry=%s",
                ws_id[:12],
                ErrorCategory.sandbox_timeout.value,
                classification.should_retry,
            )
            return _SANDBOX_TIMEOUT_TEXT
        return "code execution cancelled"
    # SB9 D3: trace is side-channel observability; a write failure MUST NOT block
    # the user from receiving the execution result. Catch + warn, never re-raise.
    try:
        eval_logger.log_sandbox_exec(
            elapsed_s=elapsed,
            exit_code=result.exit_code,
            stdout_bytes=len(result.stdout.encode("utf-8")),
            stderr_bytes=len(result.stderr.encode("utf-8")),
            sandbox_scope=scope.value,
            agent_name=agent_name,
        )
    except Exception:
        logger.warning("sandbox_exec trace write failed", exc_info=True)
    # SB6: cap each stream for the AI-facing result (trace above kept original
    # bytes). stdout/stderr have independent budgets. run_code is exempt from T4
    # (declared self_truncates) so this is the sole truncation of its output.
    # sandbox-output-redaction: redact secrets BEFORE capping so a secret straddling
    # the boundary cannot survive, and so anything spilled to disk is already redacted.
    # sandbox-large-output-spill: over-budget output is spilled to a file (full, redacted)
    # and replaced with a preview + reference, rather than dropping the middle. The trace
    # byte sizes above stay on the original (un-redacted) output as a pure volume metric.
    parts = []
    stdout = cap_or_spill(redact_secrets(result.stdout), sot.MAX_STDOUT_BYTES, label="stdout")
    if stdout:
        parts.append(stdout.rstrip())
    stderr = cap_or_spill(redact_secrets(result.stderr), sot.MAX_STDERR_BYTES, label="stderr")
    if stderr:
        parts.append(f"[stderr] {stderr.rstrip()}")
    if result.exit_code != 0:
        parts.append(f"[exit {result.exit_code}]")
    return "\n".join(parts) if parts else "(no output)"


def _origin_from_context(tool_context: ToolContext | None) -> dict[str, str | None] | None:
    """Build a scheduled-task `origin` from the inbound IM context, or None.

    Captures the creation chat so a fired reminder defaults back to where it was
    created (delivery resolves `origin` when no explicit `deliver` is set). The
    chat id is the connector's channel id (Slack channel/DM id, Telegram chat id),
    posted back via the channel path so the original thread is preserved.
    """
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    platform = getattr(sc, "platform", None) if sc else None
    chat_id = getattr(sc, "channel_name", None) if sc else None
    if not platform or not chat_id:
        return None
    return {
        "platform": platform,
        "chat_id": chat_id,
        "target_type": "channel",
        "thread_id": getattr(sc, "thread_root", None) or None,
    }


def _delivery_target_note(
    task_type: str, deliver: dict[str, str] | None, origin: dict[str, str | None] | None
) -> str:
    """Describe (or warn about) the resolved delivery target for the create echo.

    Makes a delivery-target mismatch visible at creation time (cron-delivery-governance,
    AAA-8279): explicit targets and origin fallback are named outright; a `generate` task
    with neither is a warning (not a rejection — the fire-time `no_delivery_target` error
    and failure alert from fix-cron-store-and-once are the actual safety net). `action`
    tasks deliver via their own tools and never need a scheduler-resolved target.
    """
    if deliver is not None:
        return f"投递目标: {deliver['platform']}:{deliver['target']}({deliver['target_type']})"
    if origin is not None:
        return "投递目标: 创建会话（origin）"
    if task_type == "generate":
        return (
            "⚠️ 未配置投递目标且无法从当前上下文捕获创建会话——本任务触发产出的内容将无法送达"
            "（可用 notify_target 指定，或改用 task_type=action）。"
        )
    return ""


@tool(risk_level="low")
async def schedule(
    action: Annotated[
        Literal["create", "list", "remove", "run_now", "pause", "resume", "history"],
        "要执行的操作",
    ],
    name: Annotated[str, "任务名称（create 时建议提供，便于 list 辨识）"] = "",
    schedule_kind: Annotated[
        Literal["cron", "once", "interval"],
        "调度类型：cron=周期（配 cron_expr）；once=一次性（配 run_at）；"
        "interval=每 N 秒（配 interval_seconds）",
    ] = "cron",
    cron_expr: Annotated[
        str,
        "5 段 cron『分 时 日 月 周』，各字段按 timezone 的本地钟面时间填写，"
        "切勿换算成 UTC。例：每天本地 20:34 → '34 20 * * *'",
    ] = "",
    run_at: Annotated[
        str,
        "once 的触发时刻：ISO 时间或相对时长如 '+30m'，按 timezone 的本地时间解释",
    ] = "",
    interval_seconds: Annotated[int, "interval 的间隔秒数"] = 0,
    message: Annotated[
        str,
        "generate/action 任务的指令（到点交给 agent 的 prompt）。投递目标用 notify_target 配置，"
        "勿在此写「发送给X/私信X」；generate 回复由调度器投递（勿自调发送工具），action 才自己发。",
    ] = "",
    timezone: Annotated[
        str,
        "IANA 时区名，如 'Asia/Shanghai'。cron_expr/run_at 按此时区的本地时间解释——"
        "直接填当地钟面时间，不要预先换算成 UTC；留空则用部署默认时区，"
        "仅当用户明确点名其它时区时才填",
    ] = "",
    user_id: Annotated[str, "归属用户（一般留空，由调用者身份决定）"] = "default",
    task_id: Annotated[str, "remove/run_now/pause/resume 的目标任务 ID"] = "",
    notify_platform: Annotated[str, "投递平台如 'slack'（留空则用任务创建时所在会话）"] = "",
    notify_target: Annotated[str, "投递目标 ID（频道或用户），配合 notify_platform"] = "",
    notify_target_type: Annotated[Literal["user", "channel"], "投递目标类型"] = "user",
    task_type: Annotated[
        Literal["notify", "generate", "action"],
        "notify=到点发固定文案（配 notify_text，不跑 agent）；"
        "generate=到点跑 agent 生成内容并自动广播回复（默认，适合拉取/汇总/发送类）；"
        "action=到点跑 agent 用自身工具行动，调度器不广播回复",
    ] = "generate",
    notify_text: Annotated[str, "notify 类型的固定文案（task_type=notify 时必填）"] = "",
    tool_context: ToolContext | None = None,
) -> str:
    """Manage scheduled tasks. ``action`` is one of create/list/remove/run_now/pause/resume.

    create: `schedule_kind` MUST be exactly one of `cron` / `once` / `interval` —
    - `cron`: recurring, set `cron_expr` (e.g. '0 9 * * 1-5');
    - `once`: one-time, set `schedule_kind="once"` and put the time in `run_at` (ISO time
      or a relative duration like '+30m'). Do NOT set `schedule_kind` to "run_at" — that is
      the parameter name, not a kind;
    - `interval`: every N seconds, set `interval_seconds`.
    Deliver target: notify_platform/notify_target (target_type user|channel); else defaults
    to the chat the task was created in. Delivery is CONFIGURED via notify_target, never written
    into `message` — a `generate` task's reply is delivered by the scheduler (do NOT make the
    agent self-send), while an `action` task delivers via the agent's own tools. A `generate`
    task with no notify_target whose message says "send to X" is rejected.

    Pick task_type by asking: **does the message content need information only known at send
    time?**
    - No, fixed wording → ``task_type="notify"``: provide the final polished copy in
      ``notify_text`` (NOT message). At creation time, refine the user's rough wording into
      the final copy, echo it back for confirmation, then create — at fire time the scheduler
      sends ``notify_text`` verbatim, no model run.
    - Yes, content made at fire time (summaries, fresh data) → ``task_type="generate"`` (default):
      put the instruction in ``message``; your fired reply IS what gets posted.
    - The task performs actions (send DMs/files, conditional/multi-target) → ``task_type="action"``:
      put the instruction in ``message``; you act via your own tools and the scheduler does
      NOT broadcast your reply.

    pause/resume toggle a task; remove deletes it; run_now fires it immediately; list shows all;
    history shows a task's recent run outcomes (time/status/error/duration) for the given task_id.
    """
    from fleetent import cron_scheduler

    if action == "create":
        # half-set rejection (cron-delivery-governance F4.1): notify_platform and
        # notify_target must be provided together or not at all — silently ignoring
        # a half-set previously fell back to origin, which reads as "wrong channel"
        # to the user (AAA-8279).
        if bool(notify_platform) != bool(notify_target):
            missing = "notify_platform" if notify_target else "notify_target"
            return f"error: notify_platform 和 notify_target 须成对提供（缺少 {missing}）"
        deliver = None
        if notify_platform and notify_target:
            deliver = {
                "mode": "explicit",
                "platform": notify_platform,
                "target": notify_target,
                "target_type": notify_target_type,
            }
        origin = _origin_from_context(tool_context)
        # Owner = who is acting (resolved principal), never what the model typed;
        # the user_id parameter is only a fallback for principal-less runs.
        ctx_principal = getattr(tool_context, "principal", None) if tool_context else None
        owner = ctx_principal.user_id if ctx_principal is not None else user_id
        try:
            task = cron_scheduler.create_task(
                name=name,
                cron_expr=cron_expr or None,
                timezone=timezone,
                user_id=owner,
                message=message,
                source="tool",
                schedule_kind=schedule_kind,
                run_at=run_at or None,
                interval_seconds=interval_seconds or None,
                origin=origin,
                deliver=deliver,
                task_type=task_type,
                notify_text=notify_text or None,
            )
        except ValueError as exc:
            # Per-type validation (e.g. notify without notify_text/target) → clean text,
            # never a raised exception the agent loop would have to recover from.
            return f"error: {exc}"
        target_note = _delivery_target_note(task_type, deliver, origin)
        if cron_scheduler.current() is None:
            # No live scheduler in this process — be truthful so the AI does not
            # promise the user a fire time that will never come.
            return (
                f"Scheduled task saved: id={task['id']!r} name={name!r} "
                f"kind={schedule_kind!r} — takes effect when the agent service is running "
                f"(no scheduler in this process). {target_note}"
            )
        hint = str(task.get("next_fire_hint") or "")
        return (
            f"Scheduled task created and registered: id={task['id']!r} "
            f"name={name!r} kind={schedule_kind!r}.{hint} {target_note}"
        )

    if action == "list":
        tasks = cron_scheduler.list_tasks(include_disabled=True)
        if not tasks:
            return "No scheduled tasks"
        lines = [
            f"{t['id']} | {t.get('name')} | {t.get('schedule_kind')} | "
            f"{'enabled' if t.get('enabled') else 'paused'}"
            for t in tasks
        ]
        return "\n".join(lines)

    if action == "remove":
        deleted = cron_scheduler.remove_task(task_id)
        if not deleted:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} removed"

    if action in ("pause", "resume"):
        matched = cron_scheduler.set_task_enabled(task_id, action == "resume")
        if not matched:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} {action}d"

    if action == "run_now":
        fired = await cron_scheduler.run_task_now(task_id)
        if not fired:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} fired"

    if action == "history":
        runs = cron_scheduler.list_runs(task_id, limit=20)
        if not runs:
            known = any(
                t["id"] == task_id for t in cron_scheduler.list_tasks(include_disabled=True)
            )
            if not known:
                return f"error: task {task_id!r} not found"
            return f"No runs yet for task {task_id!r}"
        lines = []
        for r in runs:
            err = r.get("agent_error") or r.get("delivery_error") or ""
            dur = r.get("duration_ms")
            dur_txt = f" {dur}ms" if dur is not None else ""
            suffix = f" — {err}" if err else ""
            lines.append(f"{r.get('fired_at')} | {r.get('status')}{dur_txt}{suffix}")
        return "\n".join(lines)

    return f"error: unknown action {action!r} (use create/list/remove/run_now/pause/resume/history)"


@tool(risk_level="low")
async def generate_image(
    prompt: str, size: str = "", tool_context: ToolContext | None = None
) -> str:
    """Generate an image from a text prompt via the self-hosted images endpoint.

    Returns a workspace-relative reference (`generated/<name>.png`) to the saved
    image, never inline base64 or a host-absolute path. On endpoint failure/timeout,
    returns an explicit error result for the AI to handle rather than raising and
    breaking the loop.
    """
    try:
        data = await image_gen_client.generate(prompt, size=size or None)
    except image_gen_client.ImageGenError as exc:
        return f"error: image generation failed: {exc}"
    ref = _save_image(data, tool_context)
    return f"image generated: {ref}"


@tool(risk_level="low")
async def analyze_image(ref: str, instruction: str, tool_context: ToolContext | None = None) -> str:
    """Understand an image on demand via the self-hosted vision endpoint.

    `ref` is a stored-image reference (a workspace-relative `uploads/<name>` produced
    when an inbound image was saved; legacy host-absolute refs still resolve);
    `instruction` is what to look for (e.g. "read the invoice total"). Returns a
    structured text description, never inline base64. Use this to re-examine or
    compare images already in the conversation. On invalid ref, unconfigured
    endpoint, or endpoint failure, returns an explicit error result for the AI to
    handle rather than raising and breaking the loop.
    """
    try:
        data = _read_upload(ref, tool_context)
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


@tool(risk_level="none")
async def invoke_agent(
    agent_name: str, message: str, tool_context: ToolContext | None = None
) -> str:
    """Delegate a message to another named agent and return its reply."""
    # Lazy import: the loop imports tools at module load (circular otherwise).
    from fleetent.runtime import load_active
    from fleetent.runtime import loop as agent_loop

    snapshot = load_active(agent_name)
    if snapshot is None:
        return f"agent {agent_name!r} not found"
    messages = [
        {"role": "system", "content": snapshot.system_prompt},
        {"role": "user", "content": message},
    ]
    # Identity-port「继承」: forward the current turn's Principal to the called agent
    # so the internal call is not principal-less (tenant_id stays bound, no re-auth).
    principal = getattr(tool_context, "principal", None) if tool_context else None
    # Parameter-style run (next<-main integration chose params over snapshot): the
    # system prompt rides in `messages`; pass the snapshot's allowlist + name through.
    return await agent_loop.run(
        messages,
        principal=principal,
        is_sub_agent=True,
        allowed_tools=snapshot.allowed_tools,
        agent_name=agent_name,
        model_policy=snapshot.model_policy,
    )


def _resolve_self_dm_redirect(
    target: str, target_type: str, address: Any, sender_id: str
) -> dict[str, Any] | None:
    """Pin a channel self-DM back to the current conversation (channel thread).

    Closes the channel→DM drift (fix-send-im-channel-self-dm-routing): when the agent
    targets the current-conversation sender as a `user` DM but the conversation lives in a
    **channel**, the delivery should land in that channel thread (the same surface `send_file`
    uses), not the sender's private DM. The approval level is unchanged — this is still the
    current conversation.

    Channel is detected via ``address.chat_type == "channel"`` (the reliable field), not
    ``address.target_type`` (latently hardcoded by the Slack adapter).

    Args:
        target: The model-supplied recipient id.
        target_type: The model-supplied target kind (`user` / `channel`).
        address: The current conversation address (duck-typed: ``chat_type``/``chat_id``/
            ``thread_id``), or None when no authoritative address is injected.
        sender_id: The current conversation's sender id.

    Returns:
        A delivery override ``{"recipient", "target_type", "thread"}`` pinning the send to the
        channel thread, or None when the rewrite does not apply (third party, channel post,
        DM conversation, missing address, or empty ids).
    """
    if address is None or target_type != "user":
        return None
    if getattr(address, "chat_type", "") != "channel":
        return None
    t, s = str(target or "").strip(), str(sender_id or "").strip()
    if not t or not s or t != s:
        return None
    return {
        "recipient": str(getattr(address, "chat_id", "") or ""),
        "target_type": "channel",
        "thread": getattr(address, "thread_id", None),
    }


@tool(risk_level="medium")
async def send_im_message(
    target: str,
    text: str,
    target_type: str = "user",
    platform: str = "",
    files: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Proactively send an IM message — optionally with file attachments — to ANOTHER user/channel.

    Use this for proactive outreach **beyond the current conversation**: notifying or messaging
    a different user, or posting to a different channel. To reply to the person you are talking
    with, do NOT use this tool — reply with plain text, or use `send_file` for a file (both land
    in the current conversation automatically). `target_type` is "user" for a DM (default) or
    "channel" for a channel post. With `target_type="user"`, `target` MUST be a user id (Slack
    `U…`, Telegram chat id) — NOT a DM channel id: Slack's `users_search` returns both a
    `UserID` (`U…`) and a `DMChannelID` (`D…`); pass the `U…`. With `target_type="channel"`,
    `target` is the channel id (Slack `C…`/`G…`). `platform` defaults to the current
    conversation's platform. `files` is an optional list of workspace-relative or
    `/exchange/<server_id>/...` paths to attach.
    Outreach to a third party is approval-gated, and the approval authorizes cross-scope
    artifacts; a send to the current conversation sender from within a channel is delivered to
    that channel thread (not a private DM).
    """
    # Lazy import: keeps module load light and avoids cycles (builtin convention).
    from fleetent import outbound
    from fleetent.governance import approval_policy

    # No self-delivery to the current conversation (outbound-tool-no-self-conversation-send):
    # replying to the current conversation is the harness's job — it delivers the final text
    # reply automatically. A send_im_message whose target IS the current conversation would
    # duplicate that reply, so it is a no-op here. risk_for == "none" iff the target resolves
    # to the current conversation (and fails closed to "medium" without a session context),
    # so this never suppresses genuine outreach to a third party.
    if (
        approval_policy.risk_for(
            "send_im_message",
            {"target": target, "target_type": target_type},
            tool_context,
            fallback="medium",
        )
        == "none"
    ):
        return (
            "（未发送）回复当前对话无需调用本工具——直接输出文本即可，平台会自动发回当前会话；"
            "如需发文件请用 send_file。send_im_message 仅用于主动发给其他用户/频道。"
        )

    connectors = tool_context.outbound_connectors if tool_context else {}
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    resolved_platform = platform or str(getattr(sc, "platform", "") or "")
    if not resolved_platform:
        return "发送失败：未指定平台且当前会话无平台信息，请显式传入 platform。"
    connector = connectors.get(resolved_platform)
    if connector is None:
        return (
            f"发送失败：当前通道不支持主动外发（无可用 {resolved_platform} 连接器）。"
            "该功能仅在 IM 网关运行时可用。"
        )
    # Conversation-pinning (fix-send-im-channel-self-dm-routing): a self-DM
    # (target == sender, target_type == "user") issued from within a CHANNEL must land in that
    # channel thread — the same surface send_file uses — not the sender's private DM. The
    # approval level is unchanged (still the current conversation; _gated below keeps using the
    # original target/target_type). Non-self / channel-post / DM-conversation sends are untouched.
    _addr = getattr(tool_context, "conversation_address", None) if tool_context else None
    _redirect = _resolve_self_dm_redirect(
        target, target_type, _addr, str(getattr(sc, "sender_id", "") or "")
    )
    eff_target = _redirect["recipient"] if _redirect else target
    eff_target_type = _redirect["target_type"] if _redirect else target_type
    eff_thread = _redirect["thread"] if _redirect else None

    if eff_target_type == "user":
        reachable = await outbound.is_reachable(resolved_platform, connector, eff_target)
        if not reachable:
            return (
                f"发送失败：目标 {eff_target} 在 {resolved_platform} 上不可达/无法触达"
                "（Telegram 用户需先与 bot 对话过）。"
            )
    sent = await outbound.send_to(
        resolved_platform,
        connector,
        eff_target,
        text,
        target_type=eff_target_type,
        thread=eff_thread,
    )
    _record_delivery(tool_context, sent)
    if not sent.ok:
        return f"发送失败：{resolved_platform} 投递 {eff_target} 时出错，请稍后重试。"
    kind = "私信" if eff_target_type == "user" else "频道消息"

    # Attachments (§7): resolve each through the shared kernel. Cross-scope artifacts are
    # authorized only when this call was approval-gated — under the recipient-identity axis
    # (approval-boundary-redesign) a send to the current conversation is NOT gated, so it must
    # not silently authorize another session's file. The call is gated iff the policy bands it
    # medium (target ≠ current conversation). Per-file degrade: a bad/cross-scope/gone entry is
    # skipped with a note, never aborting the send.
    from fleetent.governance import approval_policy

    _gated = (
        approval_policy.risk_for(
            "send_im_message",
            {"target": target, "target_type": target_type},
            tool_context,
            fallback="medium",
        )
        == "medium"
    )
    delivered, skipped = 0, []
    for raw in files or []:
        try:
            host = _resolve_outbound_path(raw, tool_context, approved=_gated)
            rcpt = await outbound.send_file_to(
                resolved_platform,
                connector,
                eff_target,
                str(host),
                target_type=eff_target_type,
                thread=eff_thread,
            )
        except Exception as exc:  # noqa: BLE001 — per-file degrade, never abort the batch
            skipped.append(f"{raw}（{exc}）")
            continue
        _record_delivery(tool_context, rcpt)
        if rcpt.ok:
            delivered += 1
        else:
            skipped.append(f"{raw}（{rcpt.error or '投递失败'}）")

    result = f"已发送{kind}到 {resolved_platform}:{eff_target}。"
    if files:
        result += f" 附件 {delivered}/{len(files)} 已投递。"
        if skipped:
            result += " 跳过：" + "；".join(skipped)
    return result


def _record_delivery(tool_context: Any, receipt: Any) -> None:
    """Append a delivery receipt to the run ledger + record its delivery trace (§2).

    Best-effort and side-channel: feeds the fact trailer (run ledger) and audit (trace).
    A None ledger (direct/non-loop call) just skips collection; tracing needs a run_id."""
    ledger = getattr(tool_context, "delivery_ledger", None)
    if ledger is not None:
        ledger.append(receipt)
    run_id = getattr(tool_context, "run_id", None)
    if run_id:
        from fleetent.observability import traces

        traces.record_delivery(
            run_id,
            getattr(tool_context, "session_id", None),
            {
                "ok": receipt.ok,
                "platform": receipt.platform,
                "target": receipt.target,
                "target_type": receipt.target_type,
                "kind": receipt.kind,
                "provider_ref": receipt.provider_ref,
                "error": receipt.error,
            },
        )


def _resolve_outbound_path(path: str, tool_context: Any, *, approved: bool) -> Path:
    """Resolve a send path to a host file across both roots — the shared delivery kernel.

    Workspace-relative paths resolve via the same fence the file tools use; `/exchange`
    paths resolve through the ledger with attribution. ``approved`` is the only cross-scope
    exemption: send_file passes False (it is never gated, so cross-scope is hard-refused);
    send_im_message passes True only when the call was approval-gated (recipient ≠ current
    conversation), so a human approval authorizes the cross-scope delivery. Raises
    ValueError / ExchangeResolutionError / FileNotFoundError.
    """
    from fleetent.tools.file_sandbox_io import resolve_host_path
    from fleetent.tools.file_tools import _is_exchange_path

    if _is_exchange_path(path):
        from fleetent import artifact_exchange

        scope_key = getattr(tool_context, "scope_key", None)
        return artifact_exchange.resolve(path, scope_key, approved=approved)
    _scope, root = _workspace_scope_and_root(tool_context)
    host = resolve_host_path(root, path)
    if not host.is_file():
        raise FileNotFoundError(f"workspace 内不存在文件 {path!r}（请确认已写入）")
    return host


@tool(risk_level="none")
async def send_file(path: str, tool_context: ToolContext | None = None) -> str:
    """Send a product file back to the current conversation's sender.

    Use this to deliver a file to the person you are talking with. `path` is either a
    **workspace-relative** path (the `/workspace` root) or an **`/exchange/<server_id>/...`**
    canonical path (a file an MCP tool produced). It is resolved to the real host file and
    sent as an attachment. The recipient is fixed to the current sender — you cannot specify
    one. Files owned by this run send directly (DM or the current channel, no approval); a
    cross-scope artifact (owned by another session) is refused — deliver it via
    send_im_message (which is approval-gated) instead.
    """
    # Recipient is harness-fixed from session_context; the model cannot supply it. No
    # session_context = no recipient (scheduled task / sub_agent) → decline.
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    if sc is None:
        return (
            "无法发送：当前运行路径无会话发起人，无法自动外发文件"
            "（如 scheduled task / sub_agent）。"
        )

    # send_file always replies to the current conversation, so it is never approval-gated
    # (approval-boundary-redesign). It therefore has no approval escape for cross-scope
    # artifacts: resolve with approved=False — a file owned by another scope is hard-refused
    # (the resolver's message points to send_im_message).
    try:
        host_path = _resolve_outbound_path(path, tool_context, approved=False)
    except (ValueError, FileNotFoundError) as exc:
        return f"无法发送：{exc}"

    # Recipient = the current conversation address, the same one text replies use, so a file
    # lands where the conversation lives: channel -> that channel (threaded), DM -> that DM
    # (send-file-to-conversation). When no authoritative address is injected (standalone CLI /
    # streaming / no gateway), fall back to the sender's DM (legacy behavior).
    address = getattr(tool_context, "conversation_address", None) if tool_context else None
    if address is not None:
        platform = str(getattr(address, "platform", "") or getattr(sc, "platform", "") or "")
        recipient = str(getattr(address, "chat_id", "") or "")
        target_type = str(getattr(address, "target_type", "user") or "user")
        thread = getattr(address, "thread_id", None)
    else:
        platform = str(getattr(sc, "platform", "") or "")
        recipient = str(getattr(sc, "sender_id", "") or "")
        target_type = "user"
        thread = None
    connectors = tool_context.outbound_connectors if tool_context else {}
    connector = connectors.get(platform)
    if connector is None:
        from fleetent import outbound_connectors as _oc

        managed = _oc.is_node_managed_runtime()
        if managed:
            # agent-hosted-im (D5): under managed placement a live connector is expected — its
            # absence is a real fault (supervisor未起/IM token 缺失), surfaced with diagnostics.
            logger.error(
                "send_file_no_connector_under_managed platform=%s managed=%s", platform, managed
            )
            return (
                f"外发失败：托管运行时无可用 {platform or '?'} 连接器（agent 自持 IM supervisor "
                "未注册连接，可能缺少/无效的 IM token）。已记录诊断，请检查 agent IM 配置。"
            )
        return (
            f"当前通道不支持主动外发文件（无可用 {platform or '?'} 连接器）。"
            "该功能仅在 IM 网关运行时可用。"
        )

    # Lazy import: keeps module load light and avoids cycles (builtin convention).
    from fleetent import outbound

    try:
        sent = await outbound.send_file_to(
            platform, connector, recipient, str(host_path), target_type=target_type, thread=thread
        )
    except Exception as exc:  # noqa: BLE001 — outbound must never abort the agent run
        logger.warning("send_file delivery error on %s: %s", platform, exc)
        return f"外发失败：{platform} 投递文件时出错，请稍后重试。"
    _record_delivery(tool_context, sent)
    if not sent.ok:
        return f"外发失败：{platform} 投递文件给 {recipient} 时出错，请稍后重试。"
    return f"已把文件发送给 {platform}:{recipient}。"
