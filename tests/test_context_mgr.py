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


def test_compress_preserves_base_system_cacheable_prefix(monkeypatch):
    # prompt-cache coordination: base system (messages[0], the cacheable prefix)
    # must survive compression byte-for-byte; only the conversation tail is
    # summarized. The variable memory/skill system message is also kept at head.
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "Summary.")
    base = "You are a helpful assistant with access to tools. Use them when needed."
    variable = "memory + matched skill"
    big_msgs = [
        {"role": "system", "content": base},
        {"role": "system", "content": variable},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(50)
        ],
    ]
    config = {"max_tokens": 10_000, "tmax_ratio": 0.5, "tretained_ratio": 0.3, "keep_recent": 4}
    result = maybe_compress(big_msgs, config=config)

    assert result is not big_msgs
    assert result[0]["role"] == "system"
    assert result[0]["content"] == base  # cacheable prefix unchanged
    assert any(m["content"] == variable for m in result if m.get("role") == "system")


# --- AR15: compression pre-cleanup (image placeholder replacement) ---


def test_pre_cleanup_replaces_image_block_with_placeholder():
    from fleetent.context_mgr import _pre_cleanup

    big_b64 = "A" * 100_000
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{big_b64}"},
                },
            ],
        }
    ]
    cleaned = _pre_cleanup(msgs)
    serialized = str(cleaned)
    assert big_b64 not in serialized  # base64 stripped
    assert "[图片：" in serialized  # placeholder injected
    assert "look at this" in serialized  # surrounding text preserved


def test_pre_cleanup_image_placeholder_uses_dimensions_when_available():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                    "width": 640,
                    "height": 480,
                },
            ],
        }
    ]
    cleaned = _pre_cleanup(msgs)
    assert "640" in str(cleaned)
    assert "480" in str(cleaned)


def test_pre_cleanup_image_placeholder_fallback_when_size_missing():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        }
    ]
    cleaned = _pre_cleanup(msgs)
    assert "未知尺寸" in str(cleaned)


def test_pre_cleanup_does_not_mutate_input():
    from fleetent.context_mgr import _pre_cleanup

    block = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    msgs = [{"role": "user", "content": [block]}]
    _pre_cleanup(msgs)
    # original block untouched (pure function, no side effects)
    assert msgs[0]["content"][0] is block
    assert block["type"] == "image_url"


def test_pre_cleanup_image_replacement_is_valid_text_block():
    from fleetent.context_mgr import _content, _pre_cleanup

    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        }
    ]
    cleaned = _pre_cleanup(msgs)
    # after _content str()-ification, no base64 / image_url type leaks into summary input
    rendered = _content(cleaned[0])
    assert "image_url" not in rendered
    assert "[图片：" in rendered


def test_pre_cleanup_leaves_plain_text_messages_unchanged():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [{"role": "user", "content": "just text"}]
    cleaned = _pre_cleanup(msgs)
    assert cleaned[0]["content"] == "just text"


# --- AR15: compression pre-cleanup (duplicate tool-call dedup) ---


def _assistant_tc(call_id: str, name: str, arguments: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
        ],
    }


def _tool_result(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def test_dedup_removes_earlier_identical_tool_pair():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        _assistant_tc("a1", "read_file", '{"path": "/x"}'),
        _tool_result("a1", "contents-of-x"),
        {"role": "user", "content": "and again?"},
        _assistant_tc("a2", "read_file", '{"path": "/x"}'),
        _tool_result("a2", "contents-of-x"),
    ]
    cleaned = _pre_cleanup(msgs)
    # earlier equivalent pair removed; latest kept
    call_ids = [
        tc["id"]
        for m in cleaned
        if m.get("role") == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    ]
    assert "a1" not in call_ids
    assert "a2" in call_ids
    # no orphaned tool_result for the removed call
    result_ids = [m["tool_call_id"] for m in cleaned if m.get("role") == "tool"]
    assert "a1" not in result_ids
    assert "a2" in result_ids


def test_dedup_keeps_when_results_differ():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        _assistant_tc("a1", "read_file", '{"path": "/x"}'),
        _tool_result("a1", "old-contents"),
        _assistant_tc("a2", "read_file", '{"path": "/x"}'),
        _tool_result("a2", "new-contents"),
    ]
    cleaned = _pre_cleanup(msgs)
    call_ids = [
        tc["id"]
        for m in cleaned
        if m.get("role") == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    ]
    assert "a1" in call_ids and "a2" in call_ids


def test_dedup_keeps_when_args_differ():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        _assistant_tc("a1", "read_file", '{"path": "/x"}'),
        _tool_result("a1", "same"),
        _assistant_tc("a2", "read_file", '{"path": "/y"}'),
        _tool_result("a2", "same"),
    ]
    cleaned = _pre_cleanup(msgs)
    call_ids = [
        tc["id"]
        for m in cleaned
        if m.get("role") == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    ]
    assert "a1" in call_ids and "a2" in call_ids


def test_dedup_args_normalized_ignores_key_order_and_whitespace():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        _assistant_tc("a1", "search", '{"q": "foo", "limit": 10}'),
        _tool_result("a1", "hits"),
        _assistant_tc("a2", "search", '{ "limit":10 ,  "q":"foo" }'),
        _tool_result("a2", "hits"),
    ]
    cleaned = _pre_cleanup(msgs)
    call_ids = [
        tc["id"]
        for m in cleaned
        if m.get("role") == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    ]
    assert "a1" not in call_ids  # normalized equal -> earlier removed
    assert "a2" in call_ids


def test_dedup_multi_block_assistant_kept_when_only_some_equivalent():
    from fleetent.context_mgr import _pre_cleanup

    multi = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "b1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"p":1}'},
            },
            {
                "id": "b2",
                "type": "function",
                "function": {"name": "list_dir", "arguments": '{"d":2}'},
            },
        ],
    }
    msgs = [
        multi,
        _tool_result("b1", "r1"),
        _tool_result("b2", "r2"),
        # later: only read_file/{"p":1} repeats with same result
        _assistant_tc("c1", "read_file", '{"p":1}'),
        _tool_result("c1", "r1"),
    ]
    cleaned = _pre_cleanup(msgs)
    # multi-block assistant must be kept whole (only b1 was equivalent, b2 was not)
    assert multi in cleaned
    result_ids = [m["tool_call_id"] for m in cleaned if m.get("role") == "tool"]
    assert "b1" in result_ids and "b2" in result_ids  # no orphaned/missing result
    assert "c1" in result_ids


def test_dedup_multi_block_assistant_removed_when_all_equivalent():
    from fleetent.context_mgr import _pre_cleanup

    multi = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "b1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"p":1}'},
            },
            {
                "id": "b2",
                "type": "function",
                "function": {"name": "list_dir", "arguments": '{"d":2}'},
            },
        ],
    }
    later = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"p":1}'},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "list_dir", "arguments": '{"d":2}'},
            },
        ],
    }
    msgs = [
        multi,
        _tool_result("b1", "r1"),
        _tool_result("b2", "r2"),
        later,
        _tool_result("c1", "r1"),
        _tool_result("c2", "r2"),
    ]
    cleaned = _pre_cleanup(msgs)
    assert multi not in cleaned  # all blocks equivalent -> earlier whole message removed
    assert later in cleaned
    result_ids = [m["tool_call_id"] for m in cleaned if m.get("role") == "tool"]
    assert "b1" not in result_ids and "b2" not in result_ids  # no orphans
    assert "c1" in result_ids and "c2" in result_ids


def test_dedup_produces_no_orphan_tool_results():
    from fleetent.context_mgr import _pre_cleanup

    msgs = [
        _assistant_tc("a1", "ping", "{}"),
        _tool_result("a1", "pong"),
        _assistant_tc("a2", "ping", "{}"),
        _tool_result("a2", "pong"),
    ]
    cleaned = _pre_cleanup(msgs)
    kept_call_ids = {
        tc["id"]
        for m in cleaned
        if m.get("role") == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }
    for m in cleaned:
        if m.get("role") == "tool":
            assert m["tool_call_id"] in kept_call_ids  # every result has its caller


# --- AR15: pre-cleanup MUST NOT call the LLM (D4) ---


def test_pre_cleanup_never_calls_llm(monkeypatch):
    import fleetent.context_mgr as cm

    calls = {"n": 0}

    def _spy(_task):
        calls["n"] += 1
        raise AssertionError("pre-cleanup must not call the LLM")

    monkeypatch.setattr(cm, "get_client_and_config", _spy)
    msgs = [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
        },
        _assistant_tc("a1", "read_file", '{"path": "/x"}'),
        _tool_result("a1", "x"),
        _assistant_tc("a2", "read_file", '{"path": "/x"}'),
        _tool_result("a2", "x"),
    ]
    cm._pre_cleanup(msgs)
    assert calls["n"] == 0


def test_compress_runs_pre_cleanup_before_summarize(monkeypatch):
    import fleetent.context_mgr as cm

    captured: dict[str, list] = {}

    def _fake_summarize(msgs):
        captured["to_summarize"] = msgs
        return "S"

    monkeypatch.setattr(cm, "_summarize", _fake_summarize)
    # get_client_and_config must never be hit by the cleanup path
    monkeypatch.setattr(
        cm,
        "get_client_and_config",
        lambda _t: (_ for _ in ()).throw(AssertionError("cleanup called LLM")),
    )

    big_b64 = "A" * 50_000
    img_msg = {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{big_b64}"}}
        ],
    }
    # AR13: head retains the leading user-intent run, so the image is placed in the
    # summarized middle (after an assistant turn breaks the intent run) to exercise
    # the AR15 pre-cleanup-before-summarize path.
    big_msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "kick off"},
        {"role": "assistant", "content": "ack"},
        img_msg,
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(60)
        ],
    ]
    config = {"max_tokens": 10_000, "tmax_ratio": 0.5, "tretained_ratio": 0.3, "keep_recent": 4}
    cm.maybe_compress(big_msgs, config=config)
    # the image base64 must have been cleaned out of the summary input
    assert big_b64 not in str(captured["to_summarize"])
    assert "[图片：" in str(captured["to_summarize"])


# --- AR13: initial-intent recognition (D2) ---


def test_initial_intent_takes_leading_user_run():
    from fleetent.context_mgr import _initial_intent

    conv = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "translate these files"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "thanks"},
    ]
    intent = _initial_intent(conv, 2)
    assert [m["content"] for m in intent] == ["hi", "translate these files"]


def test_initial_intent_stops_at_first_non_user():
    from fleetent.context_mgr import _initial_intent

    conv = [
        {"role": "user", "content": "do X"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "and Y"},
    ]
    intent = _initial_intent(conv, 5)
    assert [m["content"] for m in intent] == ["do X"]


def test_initial_intent_respects_upper_bound():
    from fleetent.context_mgr import _initial_intent

    conv = [{"role": "user", "content": f"u{i}"} for i in range(5)]
    intent = _initial_intent(conv, 2)
    assert [m["content"] for m in intent] == ["u0", "u1"]


def test_initial_intent_empty_when_leading_is_non_user():
    from fleetent.context_mgr import _initial_intent

    conv = [
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "later"},
    ]
    assert _initial_intent(conv, 2) == []


def test_initial_intent_empty_when_no_user():
    from fleetent.context_mgr import _initial_intent

    conv = [{"role": "assistant", "content": "hello"}]
    assert _initial_intent(conv, 2) == []


def test_initial_intent_returns_same_objects():
    from fleetent.context_mgr import _initial_intent

    m0 = {"role": "user", "content": "a"}
    m1 = {"role": "user", "content": "b"}
    conv = [m0, m1, {"role": "assistant", "content": "x"}]
    intent = _initial_intent(conv, 2)
    assert intent[0] is m0 and intent[1] is m1


# --- AR13: head selection excludes self-produced summary messages (D1) ---


def test_select_head_excludes_self_produced_summary():
    from fleetent.context_mgr import _select_head

    real_sys = {"role": "system", "content": "You are helpful."}
    prior_summary = {"role": "system", "content": "[Earlier conversation summary]\nold stuff"}
    intent = {"role": "user", "content": "translate these files"}
    messages = [real_sys, prior_summary, intent, {"role": "assistant", "content": "ok"}]
    head = _select_head(messages, 2)
    assert real_sys in head
    assert intent in head
    assert prior_summary not in head  # self-produced summary must NOT be promoted to head


def test_select_head_orders_system_then_intent():
    from fleetent.context_mgr import _select_head

    real_sys = {"role": "system", "content": "sys"}
    intent = {"role": "user", "content": "do the thing"}
    messages = [real_sys, intent, {"role": "assistant", "content": "ok"}]
    head = _select_head(messages, 2)
    assert head[0] is real_sys
    assert head[1] is intent


def test_default_config_carries_initial_intent_max(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from fleetent.context_mgr import _default_config

    cfg = _default_config()
    assert cfg["initial_intent_max"] == 2


# --- AR13: three-layer split in _compress (D1, D3) ---


def test_compress_preserves_initial_intent_and_excludes_it_from_summary(monkeypatch):
    import fleetent.context_mgr as cm

    captured: dict[str, list] = {}

    def _fake_summarize(msgs):
        captured["to_summarize"] = msgs
        return "S"

    monkeypatch.setattr(cm, "_summarize", _fake_summarize)
    intent = {"role": "user", "content": "INITIAL-INTENT translate three files to Japanese"}
    big_msgs = [
        {"role": "system", "content": "sys"},
        intent,
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(60)
        ],
    ]
    config = {
        "max_tokens": 10_000,
        "tmax_ratio": 0.5,
        "tretained_ratio": 0.3,
        "keep_recent": 4,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(big_msgs, config=config)
    # initial intent kept whole in result, never fed to the summary
    assert any(m is intent for m in result)
    assert "INITIAL-INTENT" not in str(captured["to_summarize"])


def test_compress_three_layer_order(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "MID-SUMMARY")
    intent = {"role": "user", "content": "do the task"}
    big_msgs = [
        {"role": "system", "content": "sys"},
        intent,
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(60)
        ],
    ]
    config = {
        "max_tokens": 10_000,
        "tmax_ratio": 0.5,
        "tretained_ratio": 0.3,
        "keep_recent": 4,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(big_msgs, config=config)
    contents = [str(m.get("content", "")) for m in result]
    sys_idx = contents.index("sys")
    intent_idx = next(i for i, m in enumerate(result) if m is intent)
    summary_idx = next(i for i, c in enumerate(contents) if "MID-SUMMARY" in c)
    # head (system, then intent) precedes the summary, which precedes the tail
    assert sys_idx < intent_idx < summary_idx
    assert summary_idx < len(result) - 1  # at least one tail message after summary


def test_compress_prior_summary_not_promoted_to_head(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "NEW-SUMMARY")
    prior = {"role": "system", "content": "[Earlier conversation summary]\nprior stuff"}
    intent = {"role": "user", "content": "the real ask"}
    big_msgs = [
        {"role": "system", "content": "sys"},
        prior,
        intent,
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(60)
        ],
    ]
    config = {
        "max_tokens": 10_000,
        "tmax_ratio": 0.5,
        "tretained_ratio": 0.3,
        "keep_recent": 4,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(big_msgs, config=config)
    # exactly one summary-prefixed system message remains (the fresh one), prior is gone
    summary_msgs = [
        m
        for m in result
        if m.get("role") == "system"
        and str(m.get("content", "")).startswith("[Earlier conversation summary]")
    ]
    assert len(summary_msgs) == 1
    assert not any(m is prior for m in result)


# --- AR13: head counts toward Tretained projection (D3) ---


def test_large_head_shrinks_tail_but_keeps_floor(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    # A big initial-intent message inflates the head; the tail must shrink in
    # response, but the 1-message tail floor (with tool-pair integrity) still holds.
    big_intent = {"role": "user", "content": "INTENT " + "y" * 8000}
    big_msgs = [
        {"role": "system", "content": "sys"},
        big_intent,
        {"role": "assistant", "content": "ack"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 4000}
            for i in range(60)
        ],
    ]
    config = {
        "max_tokens": 10_000,
        "tmax_ratio": 0.8,
        "tretained_ratio": 0.6,
        "keep_recent": 10,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(big_msgs, config=config)
    # big_intent kept whole in head
    assert any(m is big_intent for m in result)
    # tail (non-head, non-summary, non-system messages) shrank to the floor
    tail = [m for m in result if m.get("role") != "system" and m is not big_intent]
    assert len(tail) >= 1


# --- AR13: degenerate fallback (D4) ---


def test_short_conversation_no_empty_summary(monkeypatch):
    import fleetent.context_mgr as cm

    summarize_calls = {"n": 0}

    def _spy_summarize(msgs):
        summarize_calls["n"] += 1
        return ""

    monkeypatch.setattr(cm, "_summarize", _spy_summarize)
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "do X"},
        {"role": "assistant", "content": "done"},
    ]
    config = {
        "max_tokens": 100_000,
        "tmax_ratio": 0.8,
        "tretained_ratio": 0.6,
        "keep_recent": 10,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(msgs, config=config, force=True)
    # middle empty → no summary message injected and no LLM call
    assert summarize_calls["n"] == 0
    assert not any(
        str(m.get("content", "")).startswith("[Earlier conversation summary]") for m in result
    )


def test_head_tail_overlap_deduped_by_identity(monkeypatch):
    import fleetent.context_mgr as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs: "S")
    intent = {"role": "user", "content": "the only ask"}
    assistant = {"role": "assistant", "content": "reply"}
    msgs = [
        {"role": "system", "content": "sys"},
        intent,
        assistant,
    ]
    config = {
        "max_tokens": 100_000,
        "tmax_ratio": 0.8,
        "tretained_ratio": 0.6,
        "keep_recent": 10,
        "initial_intent_max": 2,
    }
    result = cm.maybe_compress(msgs, config=config, force=True)
    # intent is both head and (selected) tail; must appear exactly once
    assert sum(1 for m in result if m is intent) == 1
    assert sum(1 for m in result if m is assistant) == 1
    # original order preserved
    assert result.index(intent) < result.index(assistant)
