"""JSON-RPC 2.0 protocol codec for the TUI gateway (tui-gateway 2.1)."""

import json

import pytest

from fleetent.tui import protocol as p


def test_encode_frame_is_json_plus_newline():
    frame = p.encode_frame({"a": 1})
    assert frame.endswith("\n")
    assert json.loads(frame) == {"a": 1}


def test_decode_frame_parses_line():
    assert p.decode_frame('{"jsonrpc":"2.0","id":1,"method":"send"}\n') == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "send",
    }


def test_decode_frame_bad_json_raises_parse_error():
    with pytest.raises(p.ParseError):
        p.decode_frame("not json{")


def test_make_response_shape():
    assert p.make_response(7, {"run_id": "r1"}) == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"run_id": "r1"},
    }


def test_make_error_shape():
    err = p.make_error(7, p.METHOD_NOT_FOUND, "no such method")
    assert err == {
        "jsonrpc": "2.0",
        "id": 7,
        "error": {"code": p.METHOD_NOT_FOUND, "message": "no such method"},
    }
    assert p.METHOD_NOT_FOUND == -32601
    assert p.PARSE_ERROR == -32700


def test_make_error_null_id_for_parse_error():
    # A parse error has no id to echo (the frame couldn't be read).
    err = p.make_error(None, p.PARSE_ERROR, "parse error")
    assert err["id"] is None
    assert err["error"]["code"] == -32700


def test_make_event_is_notification_with_type_and_payload():
    evt = p.make_event(p.EVENT_TEXT_DELTA, {"content": "hi"}, run_id="r1")
    assert evt["jsonrpc"] == "2.0"
    assert "id" not in evt  # notifications carry no id
    assert evt["method"] == "event"
    assert evt["params"] == {"type": "text_delta", "payload": {"content": "hi"}, "run_id": "r1"}


def test_make_event_omits_run_id_when_absent():
    evt = p.make_event(p.EVENT_GATEWAY_READY, {})
    assert evt["params"] == {"type": "gateway.ready", "payload": {}}
    assert "run_id" not in evt["params"]


def test_event_type_constants_exist():
    assert p.EVENT_GATEWAY_READY == "gateway.ready"
    assert p.EVENT_TEXT_DELTA == "text_delta"
    assert p.EVENT_TOOL_CALL == "tool_call"
    assert p.EVENT_TOOL_RESULT == "tool_result"
    assert p.EVENT_DONE == "done"
    assert p.EVENT_ERROR == "error"
    assert p.EVENT_APPROVAL_REQUIRED == "approval_required"


def test_method_constants_exist():
    assert p.METHOD_SEND == "send"
    assert p.METHOD_ABORT == "abort"
    assert p.METHOD_APPROVE == "approve"
    assert p.METHOD_SESSION_NEW == "session.new"
    assert p.METHOD_SESSION_LIST == "session.list"


def test_run_stream_event_type_maps_to_protocol_event():
    # run_stream yields {"type": "text_delta", ...}; the gateway maps the raw type
    # straight through as the protocol event type, so the set must line up 1:1.
    for raw in ("text_delta", "tool_call", "tool_result", "done", "error"):
        assert raw in p.RUN_STREAM_EVENT_TYPES
