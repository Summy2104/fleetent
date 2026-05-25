from fleetent.context_mgr import _keep_tail, estimate_tokens, maybe_compress


def _make_messages(n: int) -> list[dict]:
    return [
        {"role": "system", "content": "You are helpful."},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 500}
            for i in range(n)
        ],
    ]


def test_estimate_tokens_proportional():
    msgs = [{"role": "user", "content": "a" * 400}]
    # String repr includes dict overhead, so total is >400 chars
    tokens = estimate_tokens(msgs)
    assert tokens > 100  # Proportional to content size


def test_no_compress_below_threshold():
    msgs = _make_messages(2)
    result = maybe_compress(msgs)
    assert result is msgs  # same object, no compression


def test_compress_triggers_above_threshold(monkeypatch):
    # Patch _summarize so we don't call the real LLM in tests
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "Summary: user asked things.")

    # Build messages big enough to exceed threshold
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(100)
        ],
    ]
    config = {
        "max_tokens": 10_000,
        "compress_threshold": 0.5,
        "keep_recent": 4,
    }
    result = maybe_compress(big_msgs, config=config)

    assert result is not big_msgs  # new list
    roles = [m["role"] for m in result if isinstance(m, dict)]
    assert roles[0] == "system"  # system prompt preserved first
    assert any(
        "Summary" in str(m.get("content", "")) for m in result
    )  # summary injected
    assert len([m for m in result if m.get("role") != "system"]) <= 5  # summary + keep_recent


def test_keep_tail_identity_not_equality():
    # Two tool messages with identical content — must use identity, not equality
    tool_msg = {"role": "tool", "content": "result"}
    tool_msg2 = {"role": "tool", "content": "result"}  # equal content, different object
    caller = {"role": "assistant", "content": "call"}
    caller2 = {"role": "assistant", "content": "call"}
    msgs = [caller, tool_msg, caller2, tool_msg2]
    tail = _keep_tail(msgs, 1)
    # tail starts with tool_msg2 (last 1) → should extend back to caller2, not caller
    assert tail[0] is caller2
    assert tail[1] is tool_msg2


def test_role_with_object_attribute():
    from fleetent.context_mgr import _role

    class FakeMsg:
        role = "assistant"

    assert _role(FakeMsg()) == "assistant"


def test_content_with_object_attribute():
    from fleetent.context_mgr import _content

    class FakeMsg:
        content = "hello"

    assert _content(FakeMsg()) == "hello"


def test_content_with_none_attribute_returns_empty():
    from fleetent.context_mgr import _content

    class FakeMsg:
        content = None

    assert _content(FakeMsg()) == ""


def test_summarize_calls_llm_and_returns_content(monkeypatch):
    from unittest.mock import MagicMock

    import fleetent.context_mgr as cm

    mock_client = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.model = "haiku"
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Summary here"
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(cm, "get_client_and_config", lambda _: (mock_client, mock_cfg))

    result = cm._summarize([{"role": "user", "content": "hello"}])
    assert result == "Summary here"


def test_summarize_exception_returns_placeholder(monkeypatch):
    import fleetent.context_mgr as cm

    def raise_exc(_task):
        raise RuntimeError("no key")

    monkeypatch.setattr(cm, "get_client_and_config", raise_exc)
    result = cm._summarize([{"role": "user", "content": "hello"}])
    assert "unavailable" in result


def test_keep_tail_tool_at_index_zero_stops_extending():
    from fleetent.context_mgr import _keep_tail

    tool_msg = {"role": "tool", "content": "result"}
    msgs = [tool_msg]  # tool at index 0 — idx==0, must break
    tail = _keep_tail(msgs, 2)
    assert tail[0] is tool_msg
