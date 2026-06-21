"""Single dispatch for gateway methods (send/abort/approve/session.*).

One ``dispatch`` handles every method for a connection, so the same logic serves
any transport (design: transport-agnostic). Per-connection state (user, bound
session, in-flight ``{run_id: CancelToken}``) lives on ``Connection``; ``send``
spawns a background task that consumes ``run_stream`` and pushes each event as an
``event`` notification through the connection's transport.
"""

import asyncio
import uuid
from typing import Any, Literal, cast

from fleetent.governance import approval_router
from fleetent.identity import Principal
from fleetent.runtime import CancelToken, commands, run_stream
from fleetent.session import manager as session_mgr
from fleetent.structured_logging import get_logger
from fleetent.tui import protocol as p
from fleetent.tui.transport import Transport

_logger = get_logger("tui.dispatch")

_SESSION_PREFIX = "tui:"


def _session_prefix(user_id: str) -> str:
    return f"{_SESSION_PREFIX}{user_id}:"


def _new_session_id(user_id: str) -> str:
    return f"{_session_prefix(user_id)}{uuid.uuid4().hex[:12]}"


class Connection:
    """Per-connection gateway state.

    Holds the resolved ``Principal`` so the run path (``run_stream``) stays identity-
    bearing end-to-end (identity-port). ``user_id`` is derived from it for session
    scoping. The principal-less ``user_id`` ctor form is the no-identity baseline only.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        principal: Principal | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        if principal is None:
            principal = Principal(user_id=user_id or "default", tenant_id="default")
        self.principal = principal
        self.user_id = principal.user_id
        self.transport = transport
        self.session_id = session_id or _new_session_id(self.user_id)
        # The deployed agent this connection runs as; powers user.md injection and
        # the /user command. Set by the WS gateway from agent_app.serve's agent.
        self.agent_name = agent_name
        self.cancel_tokens: dict[str, CancelToken] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def cancel_all(self) -> None:
        """Cancel every in-flight run (connection teardown / peer-gone)."""
        for token in self.cancel_tokens.values():
            token.cancel()


async def _stream_run(
    conn: Connection, run_id: str, message: str, session_id: str, token: CancelToken
) -> None:
    """Consume ``run_stream`` and push each event as an ``event`` notification."""
    saw_terminal = False
    try:
        async for event in run_stream(
            message,
            principal=conn.principal,
            session_id=session_id,
            cancel_token=token,
            agent_name=conn.agent_name,
        ):
            event_type = str(event.get("type", ""))
            payload = {k: v for k, v in event.items() if k != "type"}
            await conn.transport.write(p.make_event(event_type, payload, run_id=run_id))
            if event_type in (p.EVENT_DONE, p.EVENT_ERROR):
                saw_terminal = True
    except Exception as exc:  # noqa: BLE001 — surface as an error event, never crash the conn
        _logger.warn("tui_run_failed", run_id=run_id, error=str(exc))
        await conn.transport.write(
            p.make_event(p.EVENT_ERROR, {"content": str(exc)}, run_id=run_id)
        )
    finally:
        conn.cancel_tokens.pop(run_id, None)
        # D4: if aborted before run_stream emitted its own terminal event, send a
        # closing `done` so the client can collapse the spinner.
        if token.is_cancelled() and not saw_terminal:
            await conn.transport.write(
                p.make_event(p.EVENT_DONE, {"content": "", "aborted": True}, run_id=run_id)
            )


def _start_run(conn: Connection, message: str, session_id: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    token = CancelToken()
    conn.cancel_tokens[run_id] = token
    task = asyncio.create_task(_stream_run(conn, run_id, message, session_id, token))
    conn._tasks.add(task)
    task.add_done_callback(conn._tasks.discard)
    return run_id


async def dispatch(conn: Connection, request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one parsed JSON-RPC request; return the response object (or None)."""
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method == p.METHOD_SEND:
        session_id = params.get("session_id") or conn.session_id
        run_id = _start_run(conn, str(params.get("message", "")), session_id)
        return p.make_response(req_id, {"run_id": run_id})

    if method == p.METHOD_ABORT:
        run_id = params.get("run_id", "")
        token = conn.cancel_tokens.get(run_id)
        if token is None:
            return p.make_response(req_id, {"ok": False, "aborted": False})
        token.cancel()
        return p.make_response(req_id, {"ok": True, "aborted": True})

    if method == p.METHOD_APPROVE:
        decision = params.get("decision")
        if decision not in ("approved", "rejected"):
            return p.make_error(req_id, p.INVALID_PARAMS, "decision must be approved|rejected")
        found = await approval_router.resolve_approval_request(
            approval_id=str(params.get("approval_id", "")),
            decision=cast(Literal["approved", "rejected"], decision),
            approver_user_id=conn.user_id,
        )
        return p.make_response(req_id, {"ok": found})

    if method == p.METHOD_SESSION_NEW:
        conn.session_id = _new_session_id(conn.user_id)
        return p.make_response(req_id, {"session_id": conn.session_id})

    if method == p.METHOD_SESSION_LIST:
        sessions = session_mgr.list_session_ids(_session_prefix(conn.user_id))
        return p.make_response(req_id, {"sessions": sessions})

    if method in (p.METHOD_COMMAND, p.METHOD_USER):
        # Both route through the shared dispatcher; METHOD_USER kept for compat.
        ctx = commands.CommandContext(
            agent_id=conn.agent_name, session_id=conn.session_id, user_id=conn.user_id
        )
        reply = await commands.handle_command(ctx, str(params.get("text", "")))
        return p.make_response(req_id, {"reply": reply or "（不是命令)"})

    return p.make_error(req_id, p.METHOD_NOT_FOUND, f"unknown method: {method}")
