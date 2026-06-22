"""Shared slash-command dispatcher for the session-bearing entrypoints.

One ``handle_command`` implements every command once; TUI and IM each call it
before entering the agent loop. A non-command returns ``None`` (proceed as normal
chat); a hit returns the user-facing receipt and the input MUST NOT run the loop
(mirrors the original ``user_instructions`` contract, now folded in here).

Session-scoped commands (``/clear`` ``/compact`` ``/context`` ``/usage`` ``/cost``)
require ``ctx.session_id``; the CLI one-shot path has no session and is rejected with
a hint rather than misfiring. ``/user`` is agent-scoped and works without a session.

Pure agent-side: reads/writes session files and reads usage traces; never a platform
table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fleetent.runtime import context, user_instructions
from fleetent.session import manager as session_mgr
from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.commands")


@dataclass
class CommandContext:
    """Per-invocation identity threaded from each entrypoint into a command."""

    agent_id: str | None
    session_id: str | None
    user_id: str | None


# handler signature: (ctx, full_text) -> receipt
_Handler = Callable[["CommandContext", str], Awaitable[str]]


@dataclass(frozen=True)
class _Entry:
    handler: _Handler
    requires_session: bool


_REGISTRY: dict[str, _Entry] = {}


def _register(name: str, *, requires_session: bool) -> Callable[[_Handler], _Handler]:
    def deco(fn: _Handler) -> _Handler:
        _REGISTRY[name] = _Entry(handler=fn, requires_session=requires_session)
        return fn

    return deco


_NO_SESSION_HINT = "当前入口没有会话上下文,该命令在此不可用。"


async def handle_command(ctx: CommandContext, text: str) -> str | None:
    """Dispatch a ``/command`` line; return a receipt, or ``None`` if not a command.

    ``None`` means ordinary chat (proceed to the agent loop). An unknown ``/word`` is
    also treated as ordinary text (returned ``None``), never silently swallowed.
    """
    stripped = (text or "").strip()
    if not stripped.startswith("/") or len(stripped) == 1:
        return None
    word = stripped[1:].split(maxsplit=1)[0]
    entry = _REGISTRY.get(word)
    if entry is None:
        return None
    if entry.requires_session and not ctx.session_id:
        return _NO_SESSION_HINT
    return await entry.handler(ctx, stripped)


@_register("user", requires_session=False)
async def _cmd_user(ctx: CommandContext, text: str) -> str:
    if not ctx.agent_id:
        return "未绑定 agent,无法管理用户指令。"
    return user_instructions.handle_user_command(ctx.agent_id, text) or "用法:/user [内容|clear]"


@_register("clear", requires_session=True)
async def _cmd_clear(ctx: CommandContext, text: str) -> str:
    # clear() takes the session lock itself; session_id is guaranteed by the guard.
    await session_mgr.clear(str(ctx.session_id))
    return "✅ 已清空当前会话的历史(仅影响这个会话)。"


@_register("compact", requires_session=True)
async def _cmd_compact(ctx: CommandContext, text: str) -> str:
    sid = str(ctx.session_id)
    async with session_mgr.session_lock(sid):
        msgs = await session_mgr.load(sid)
        before, before_tok = len(msgs), context.estimate_tokens(msgs)
        new = context.maybe_compress(
            msgs, force=True, session_id=sid, user_id=ctx.user_id, agent_name=ctx.agent_id
        )
        await session_mgr.save(sid, new)
    after, after_tok = len(new), context.estimate_tokens(new)
    return f"✅ 已压缩上下文:{before}→{after} 条消息(约 {before_tok}→{after_tok} tokens)。"


@_register("context", requires_session=True)
async def _cmd_context(ctx: CommandContext, text: str) -> str:
    from fleetent import agent_config

    msgs = await session_mgr.load(str(ctx.session_id))
    tok = context.estimate_tokens(msgs)
    agent = agent_config.current().get(ctx.agent_id) if ctx.agent_id else None
    pct = ""
    if agent is not None and agent.context_max_tokens:
        pct = f",约占上限 {agent.context_max_tokens} 的 {tok * 100 // agent.context_max_tokens}%"
    return f"📊 当前会话:{len(msgs)} 条消息,约 {tok} tokens{pct}。"


@_register("usage", requires_session=True)
async def _cmd_usage(ctx: CommandContext, text: str) -> str:
    from fleetent.observability.usage import UsageQuery, get_usage_summary

    s = get_usage_summary(UsageQuery(session_id=ctx.session_id, agent_name=ctx.agent_id))
    return (
        f"📊 本会话用量:{s.run_count} 次运行,"
        f"{s.prompt_tokens} prompt + {s.completion_tokens} completion = {s.total_tokens} tokens。"
    )


@_register("cost", requires_session=True)
async def _cmd_cost(ctx: CommandContext, text: str) -> str:
    from fleetent import agent_config
    from fleetent.observability.usage import UsageQuery, get_usage_summary

    s = get_usage_summary(UsageQuery(session_id=ctx.session_id, agent_name=ctx.agent_id))
    agent = agent_config.current().get(ctx.agent_id) if ctx.agent_id else None
    cap = agent.agent_max_tokens if agent and agent.agent_max_tokens > 0 else None
    cap_txt = f",每轮 token 上限 {cap}" if cap else ""
    # fleetent has no USD pricing model — report a token/budget view, not dollars.
    return f"💰 本会话累计约 {s.total_tokens} tokens(token/预算口径,非美元金额){cap_txt}。"
