"""JSON-RPC 2.0 protocol codec + method/event constants for the TUI gateway.

Wire format (design D2): one frame per line, ``json.dumps(obj) + "\\n"``. Requests
and responses follow JSON-RPC 2.0; server→client events are notifications with
``method == "event"`` and ``params == {type, payload, run_id?}``. The protocol is
transport-agnostic; the same frames ride any transport.
"""

import json
from typing import Any

JSONRPC_VERSION = "2.0"

# JSON-RPC error codes (subset we use).
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

# Client→server methods (requests carry an ``id``).
METHOD_SEND = "send"
METHOD_ABORT = "abort"
METHOD_APPROVE = "approve"
METHOD_SESSION_NEW = "session.new"
METHOD_SESSION_LIST = "session.list"
METHOD_USER = "user"
# Generalized slash-command method: server calls runtime.commands.handle_command.
METHOD_COMMAND = "command"

# Server→client event types (carried in an ``event`` notification's ``params.type``).
EVENT_GATEWAY_READY = "gateway.ready"
EVENT_TEXT_DELTA = "text_delta"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_DONE = "done"
EVENT_ERROR = "error"
EVENT_APPROVAL_REQUIRED = "approval_required"

# The run_stream event types the gateway maps straight through to protocol events
# (their raw ``type`` value equals the protocol event type).
RUN_STREAM_EVENT_TYPES = frozenset(
    {EVENT_TEXT_DELTA, EVENT_TOOL_CALL, EVENT_TOOL_RESULT, EVENT_DONE, EVENT_ERROR}
)


class ParseError(Exception):
    """A frame could not be decoded as JSON (maps to JSON-RPC -32700)."""


def encode_frame(obj: dict[str, Any]) -> str:
    """Serialize a protocol object to a newline-terminated JSON frame."""
    return json.dumps(obj, ensure_ascii=False) + "\n"


def decode_frame(line: str) -> dict[str, Any]:
    """Parse one wire frame into a dict, raising ``ParseError`` on malformed JSON."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc
    if not isinstance(obj, dict):
        raise ParseError("frame is not a JSON object")
    return obj


def make_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response echoing ``request_id``."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def make_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response (``id`` is null when the frame had none)."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def make_event(
    event_type: str, payload: dict[str, Any], run_id: str | None = None
) -> dict[str, Any]:
    """Build an ``event`` notification (no ``id``); ``run_id`` is included only when set."""
    params: dict[str, Any] = {"type": event_type, "payload": payload}
    if run_id is not None:
        params["run_id"] = run_id
    return {"jsonrpc": JSONRPC_VERSION, "method": "event", "params": params}
