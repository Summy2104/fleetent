"""FastAPI router for /admin/chat (playground) and /admin/sessions (governance).

Owns the management behaviour only: the admin try-run playground (isolated
origin=playground sessions, request-level overrides, playground-only approval bypass,
pin/export) and the real-session governance face (list/replay, takeover + human
inject, force-end / clear / reset, bulk disposition, export).

The while-tool-use loop / model routing / approval live in agent-runtime + governance;
transcript persistence + locks live in session; IM delivery lives in im-gateway. Those
are reached through injectable seams (mockable in tests). Session governance metadata
is persisted via session_admin_store. Never imports the agent loop directly.

Auth: reads allow viewer+admin, writes require admin; high-risk writes need X-Confirm.
"""

import datetime
import json
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent.platform.chat_management import session_admin_store, transcript_export

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
PLAYGROUND_RETENTION_DAYS = 7


# --- injectable seams (agent-runtime / session / im-gateway follow-ups) -------


def run_playground(
    agent_name: str,
    session_id: str,
    message: str,
    overrides: dict[str, Any] | None,
    bypass_medium: bool,
) -> dict[str, Any]:
    """Run one playground turn. Bridges agent_loop.run_stream on host (collected).

    Returns ``{reply, events}`` where events carry the per-turn observability
    (skill/kb hits, tool i/o, approval decisions, model routing). origin=playground
    so the run is not counted toward the agent's outward usage.
    """
    return {"reply": "", "events": [], "wired": False}


def run_playground_stream(
    agent_name: str,
    session_id: str,
    message: str,
    overrides: dict[str, Any] | None,
    bypass_medium: bool,
) -> Iterator[dict[str, Any]]:
    """Stream playground turn events (bridges agent_loop.run_stream on host).

    Yields per-turn observability event dicts; the route serializes them as SSE.
    """
    return iter(())


def session_stats(session_id: str) -> dict[str, Any]:
    """Per-session rollup for the list view (tokens / rounds / pending approvals).

    Bridges observability + permission_gate on host; placeholder returns zeros.
    """
    return {"total_tokens": 0, "rounds": 0, "pending_approvals": 0}


def load_transcript(session_id: str) -> list[dict[str, Any]]:
    """Read a session transcript (bridges session_mgr.load on host)."""
    return []


def clear_session(session_id: str) -> None:
    """Empty a session transcript (bridges session_mgr.clear)."""
    return None


def inject(session_id: str, role: str, content: str) -> None:
    """Append a human-agent message (bridges session_mgr.inject_message)."""
    return None


def reset_session(session_id: str, keep_turns: int) -> None:
    """Truncate a transcript to the first ``keep_turns`` messages (session domain)."""
    return None


def im_deliver(session_id: str, content: str) -> None:
    """Deliver a human-agent message back to the originating IM platform (im-gateway)."""
    return None


# --- auth helpers -------------------------------------------------------------


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _require_confirm(x_confirm: str | None) -> None:
    if x_confirm != "true":
        raise HTTPException(status_code=428, detail="confirmation required for high-risk action")


# --- request bodies -----------------------------------------------------------


class StartBody(BaseModel):
    agent_name: str


class MessageBody(BaseModel):
    message: str
    overrides: dict[str, Any] | None = None
    auto_approve_medium: bool = False


class PinBody(BaseModel):
    note: str | None = None


class InjectBody(BaseModel):
    content: str
    role: str = "human_agent"


class ResetBody(BaseModel):
    keep_turns: int


class BulkBody(BaseModel):
    session_ids: list[str]
    action: str  # "end" | "clear"


# --- playground ---------------------------------------------------------------


@router.post("/chat/start")
def playground_start(body: StartBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    session_id = f"pg-{uuid.uuid4().hex[:12]}"
    session_admin_store.upsert_meta(session_id, origin="playground", agent_name=body.agent_name)
    return {"session_id": session_id, "origin": "playground", "agent_name": body.agent_name}


@router.post("/chat/{session_id}/message")
def playground_message(
    session_id: str, body: MessageBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    meta = session_admin_store.get_meta(session_id)
    if meta["origin"] != "playground":
        raise HTTPException(status_code=409, detail="not a playground session")
    bypass = body.auto_approve_medium  # only honored for playground sessions
    if bypass:
        audit_log.write_audit(user.id, "playground_bypass_medium", "session", session_id)
    result = run_playground(meta["agent_name"], session_id, body.message, body.overrides, bypass)
    return result


@router.post("/chat/{session_id}/stream")
def playground_stream(
    session_id: str, body: MessageBody, authorization: str | None = Header(None)
) -> StreamingResponse:
    user = _require_admin(authorization)
    meta = session_admin_store.get_meta(session_id)
    if meta["origin"] != "playground":
        raise HTTPException(status_code=409, detail="not a playground session")
    bypass = body.auto_approve_medium
    if bypass:
        audit_log.write_audit(user.id, "playground_bypass_medium", "session", session_id)

    def _sse() -> Iterator[str]:
        for event in run_playground_stream(
            meta["agent_name"], session_id, body.message, body.overrides, bypass
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@router.post("/chat/{session_id}/pin")
def playground_pin(
    session_id: str, body: PinBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    session_admin_store.set_pinned(session_id, True, note=body.note)
    audit_log.write_audit(user.id, "playground_pin", "session", session_id)
    return {"session_id": session_id, "pinned": True}


@router.get("/chat/{session_id}/export")
def playground_export(
    session_id: str, fmt: str = "json", authorization: str | None = Header(None)
) -> Any:
    user = _require_admin(authorization)
    transcript = load_transcript(session_id)
    audit_log.write_audit(user.id, "session_export", "session", session_id, detail={"fmt": fmt})
    if fmt == "markdown":
        return Response(
            content=transcript_export.render_markdown(session_id, transcript),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{session_id}.md"'},
        )
    return {"session_id": session_id, "transcript": transcript}


def purge_expired_playground(
    now: datetime.datetime | None = None, retention_days: int = PLAYGROUND_RETENTION_DAYS
) -> dict[str, list[str]]:
    """Delete unpinned playground sessions past the retention window (scheduling job).

    Transcript is emptied through the session seam; governance metadata is dropped.
    """
    moment = now or datetime.datetime.now(datetime.UTC)
    cutoff = (moment - datetime.timedelta(days=retention_days)).isoformat()
    purged = []
    for sid in session_admin_store.list_unpinned_playground(cutoff):
        clear_session(sid)
        session_admin_store.delete_meta(sid)
        purged.append(sid)
    return {"purged": purged}


# --- session governance -------------------------------------------------------


@router.post("/sessions/bulk")
def bulk_dispose(
    body: BulkBody, authorization: str | None = Header(None), x_confirm: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    if body.action not in {"end", "clear"}:
        raise HTTPException(status_code=422, detail="action must be 'end' or 'clear'")
    batch_id = uuid.uuid4().hex
    for sid in body.session_ids:
        if body.action == "end":
            session_admin_store.set_status(sid, "ended")
        else:
            clear_session(sid)
        audit_log.write_audit(
            user.id, f"session_bulk_{body.action}", "session", sid, batch_id=batch_id
        )
    return {"batch_id": batch_id, "count": len(body.session_ids), "action": body.action}


@router.get("/sessions")
def list_sessions(
    status: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    rows = session_admin_store.list_meta(status=status, user_id=user_id, agent_name=agent_name)
    for row in rows:
        row.update(session_stats(row["session_id"]))
    return rows


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return {
        "meta": session_admin_store.get_meta(session_id),
        "transcript": load_transcript(session_id),
    }


@router.post("/sessions/{session_id}/takeover")
def takeover(session_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    session_admin_store.set_takeover(session_id, user.id)
    audit_log.write_audit(user.id, "session_takeover", "session", session_id)
    return {"session_id": session_id, "taken_over": True}


@router.post("/sessions/{session_id}/release")
def release(session_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    session_admin_store.clear_takeover(session_id)
    audit_log.write_audit(user.id, "session_release", "session", session_id)
    return {"session_id": session_id, "taken_over": False}


@router.post("/sessions/{session_id}/inject")
def inject_message(
    session_id: str, body: InjectBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    inject(session_id, body.role, body.content)
    meta = session_admin_store.get_meta(session_id)
    if meta["origin"] == "im":
        im_deliver(session_id, body.content)
    audit_log.write_audit(user.id, "session_inject", "session", session_id)
    return {"session_id": session_id, "injected": True}


@router.post("/sessions/{session_id}/force-end")
def force_end(
    session_id: str, authorization: str | None = Header(None), x_confirm: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    session_admin_store.set_status(session_id, "ended")
    audit_log.write_audit(user.id, "session_force_end", "session", session_id)
    return {"session_id": session_id, "status": "ended"}


@router.post("/sessions/{session_id}/clear")
def clear(
    session_id: str, authorization: str | None = Header(None), x_confirm: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    clear_session(session_id)
    audit_log.write_audit(user.id, "session_clear", "session", session_id)
    return {"session_id": session_id, "cleared": True}


@router.post("/sessions/{session_id}/reset")
def reset(
    session_id: str,
    body: ResetBody,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    reset_session(session_id, body.keep_turns)
    audit_log.write_audit(
        user.id, "session_reset", "session", session_id, detail={"keep_turns": body.keep_turns}
    )
    return {"session_id": session_id, "keep_turns": body.keep_turns}
