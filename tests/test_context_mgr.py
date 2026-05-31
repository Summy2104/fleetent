import pytest

from fleetent.context_mgr import (
    _keep_tail,
    compress_for_context_overflow,
    estimate_tokens,
    maybe_compress,
)


def _make_messages(n: int) -> list[dict]:
    return [
        {"role": "system", "content": "You are helpful."},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 500} for i in range(n)],
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
        "tmax_ratio": 0.5,
        "tretained_ratio": 0.3,
        "keep_recent": 4,
    }
    result = maybe_compress(big_msgs, config=config)

    assert result is not big_msgs  # new list
    roles = [m["role"] for m in result if isinstance(m, dict)]
    assert roles[0] == "system"  # system prompt preserved first
    assert any("Summary" in str(m.get("content", "")) for m in result)  # summary injected
    assert len([m for m in result if m.get("role") != "system"]) <= 5  # summary + keep_recent


def test_no_compress_when_at_or_below_tmax(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "Summary.")
    msgs = [
        {"role": "system", "content": "sys"},
        *[{"role": "user", "content": "x" * 2000} for _ in range(2)],
    ]
    # estimate well under tmax line; must return same object untouched
    config = {"max_tokens": 10_000, "tmax_ratio": 0.8, "tretained_ratio": 0.6, "keep_recent": 4}
    result = maybe_compress(msgs, config=config)
    assert result is msgs


def test_compress_triggers_when_above_tmax(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "Summary.")
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(50)
        ],
    ]
    config = {"max_tokens": 10_000, "tmax_ratio": 0.5, "tretained_ratio": 0.3, "keep_recent": 4}
    result = maybe_compress(big_msgs, config=config)
    assert result is not big_msgs


def test_compress_falls_back_to_tretained_target(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    # Many large messages; keep_recent alone (10) would stay well over tretained.
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 4000}
            for i in range(60)
        ],
    ]
    config = {"max_tokens": 10_000, "tmax_ratio": 0.8, "tretained_ratio": 0.6, "keep_recent": 10}
    result = maybe_compress(big_msgs, config=config)
    target = int(10_000 * 0.6)
    assert estimate_tokens(result) <= target


def test_compress_keeps_tool_pair_whole_even_above_target(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    caller = {"role": "assistant", "content": "c" * 4000}
    tool_res = {"role": "tool", "content": "r" * 4000}
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[{"role": "user", "content": "x" * 4000} for _ in range(30)],
        caller,
        tool_res,
    ]
    # tretained tiny so a single message already exceeds it; tool pair must stay whole.
    config = {"max_tokens": 10_000, "tmax_ratio": 0.8, "tretained_ratio": 0.05, "keep_recent": 1}
    result = maybe_compress(big_msgs, config=config)
    # The orphaned tool result must be preceded by its caller (no truncation mid-pair).
    non_system = [m for m in result if m.get("role") != "system"]
    assert tool_res in non_system
    if tool_res in non_system:
        idx = non_system.index(tool_res)
        assert non_system[idx - 1] is caller


def test_compress_spacing_below_tmax_after_compress(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 4000}
            for i in range(60)
        ],
    ]
    config = {"max_tokens": 10_000, "tmax_ratio": 0.8, "tretained_ratio": 0.6, "keep_recent": 10}
    result = maybe_compress(big_msgs, config=config)
    trigger = int(10_000 * 0.8)
    assert estimate_tokens(result) < trigger  # spacing: won't immediately re-trigger


def test_illegal_config_tretained_ge_tmax_raises():
    config = {"max_tokens": 10_000, "tmax_ratio": 0.6, "tretained_ratio": 0.6, "keep_recent": 4}
    with pytest.raises(ValueError):
        maybe_compress([{"role": "user", "content": "hi"}], config=config)


def test_manual_force_compress_below_tmax(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    # Small conversation, nowhere near tmax; force must still compress.
    msgs = [
        {"role": "system", "content": "sys"},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 200} for i in range(20)],
    ]
    config = {"max_tokens": 100_000, "tmax_ratio": 0.8, "tretained_ratio": 0.6, "keep_recent": 4}
    assert maybe_compress(msgs, config=config) is msgs  # auto: no trigger
    forced = maybe_compress(msgs, config=config, force=True)
    assert forced is not msgs
    assert any("summary" in str(m.get("content", "")).lower() for m in forced)


def test_context_overflow_entrypoint_compresses(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    msgs = [
        {"role": "system", "content": "sys"},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 200} for i in range(20)],
    ]
    config = {"max_tokens": 100_000, "tmax_ratio": 0.8, "tretained_ratio": 0.6, "keep_recent": 4}
    result = compress_for_context_overflow(msgs, config=config)
    assert result is not msgs
    assert any("summary" in str(m.get("content", "")).lower() for m in result)


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


def test_estimate_tokens_image_block_uses_fixed_placeholder():
    # A large base64 image block must not inflate the estimate by its length.
    big_b64 = "A" * 100_000
    img_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{big_b64}"}},
        ],
    }
    tokens = estimate_tokens([img_msg])
    # Far below the 25k tokens the raw base64 would otherwise contribute.
    assert tokens < 2000


def test_estimate_tokens_text_unchanged():
    msgs = [{"role": "user", "content": "a" * 400}]
    assert estimate_tokens(msgs) > 100


def test_default_config_returns_dual_threshold_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from fleetent.context_mgr import _default_config

    cfg = _default_config()
    assert cfg["tmax_ratio"] == 0.8
    assert cfg["tretained_ratio"] == 0.6
    assert "compress_threshold" not in cfg
    assert cfg["max_tokens"] == 200_000
    assert cfg["keep_recent"] == 10
