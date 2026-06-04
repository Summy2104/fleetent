"""Tests for eval_logger IM metadata fields."""

import json


def test_trace_with_im_metadata(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-1",
        messages=[{"role": "user", "content": "hi"}],
        response="hello",
        platform="slack",
        session_id="user:U123",
        channel_id="C999",
        thread_id="T456",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["platform"] == "slack"
    assert entry["session_id"] == "user:U123"
    assert entry["channel_id"] == "C999"
    assert entry["thread_id"] == "T456"


def test_trace_without_im_metadata_no_null_pollution(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-1",
        messages=[{"role": "user", "content": "hi"}],
        response="hello",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    # IM fields should not appear when not provided
    assert "platform" not in entry
    assert "session_id" not in entry
    assert "channel_id" not in entry
    assert "thread_id" not in entry
    assert "message_id" not in entry
    # Core fields must exist
    assert "user_id" in entry
    assert "reply" in entry


def test_trace_with_message_id(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")

    el.log(
        user_id="user-2",
        messages=[{"role": "user", "content": "test"}],
        response="ok",
        platform="telegram",
        message_id="MSG-789",
    )

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["platform"] == "telegram"
    assert entry["message_id"] == "MSG-789"
    assert "session_id" not in entry
    assert "channel_id" not in entry
    assert "thread_id" not in entry


def test_log_run_writes_entry(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run(
        user_input="ping",
        reply="pong",
        messages=[{"role": "user", "content": "ping"}],
        elapsed_s=0.5,
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["input"] == "ping"
    assert entry["reply"] == "pong"
    assert entry["elapsed_s"] == 0.5
    assert entry["tokens"] is None
    assert "ts" in entry


def test_log_run_with_usage(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15
    el.log_run("hi", "hello", [], 0.1, usage=usage)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["tokens"] == {"prompt": 10, "completion": 5, "total": 15}


def test_serialize_model_dump():
    from fleetent.eval_logger import _serialize

    class FakeMsg:
        def model_dump(self):
            return {"role": "assistant", "content": "reply"}

    assert _serialize(FakeMsg()) == {"role": "assistant", "content": "reply"}


def test_serialize_fallback_str():
    from fleetent.eval_logger import _serialize

    class Unknown:
        def __str__(self):
            return "custom_repr"

    assert _serialize(Unknown()) == "custom_repr"


# --- model_used ---


def test_log_run_model_used_written_to_trace(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, model_used="claude-haiku-4-5")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["model_used"] == "claude-haiku-4-5"


def test_log_run_model_used_omitted_when_not_provided(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "model_used" not in entry


# --- error_category ---


def test_log_run_error_category_written_to_trace(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, error_category="rate_limit")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["error_category"] == "rate_limit"


def test_log_run_error_category_omitted_when_not_provided(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "error_category" not in entry


# --- user_id ---


def test_log_run_user_id_written(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, user_id="user-42")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["user_id"] == "user-42"


def test_log_run_user_id_omitted_when_not_provided(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "user_id" not in entry


# --- agent_name ---


def test_log_run_agent_name_written(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, agent_name="support-bot")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["agent_name"] == "support-bot"


def test_log_run_agent_name_omitted_when_not_provided(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "agent_name" not in entry


# --- hygiene_repairs (AR6) ---


def test_log_run_hygiene_repairs_written(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1, hygiene_repairs={"merged_same_role": 2})
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["hygiene_repairs"] == {"merged_same_role": 2}


def test_log_run_hygiene_repairs_omitted_when_not_provided(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "hygiene_repairs" not in entry


# --- D6: merged trace path constant (single isolation point) ---


def test_log_run_and_log_share_single_trace_constant(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    # The merged constant must be the only path both writers use, so monkeypatching
    # it once isolates every write. A second alias constant would reintroduce the
    # "isolated one, leaked the other" gap D6 closes.
    assert not hasattr(el, "_LOG_PATH")

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("ping", "pong", [], 0.1)
    el.log(user_id="u1", messages=[{"role": "user", "content": "hi"}], response="ok")

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


# --- D5: unified taxonomy (kind) ---


def test_log_run_includes_kind_agent_run(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("hi", "hello", [], 0.1)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["kind"] == "agent_run"


def test_log_run_kind_is_pure_addition(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("ping", "pong", [{"role": "user", "content": "ping"}], 0.5, user_id="u-1")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    # Existing fields keep their values/structure; only `kind` is added.
    assert entry["input"] == "ping"
    assert entry["reply"] == "pong"
    assert entry["elapsed_s"] == 0.5
    assert entry["tokens"] is None
    assert entry["user_id"] == "u-1"
    assert "ts" in entry
    assert set(entry) == {
        "ts",
        "input",
        "reply",
        "messages",
        "elapsed_s",
        "tokens",
        "user_id",
        "kind",
    }


def test_log_includes_kind_im_message(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log(user_id="u1", messages=[{"role": "user", "content": "hi"}], response="ok")
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["kind"] == "im_message"


def test_log_kind_is_pure_addition(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log(
        user_id="u1", messages=[{"role": "user", "content": "hi"}], response="ok", platform="slack"
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["user_id"] == "u1"
    assert entry["reply"] == "ok"
    assert entry["platform"] == "slack"
    assert "ts" in entry
    assert set(entry) == {"ts", "user_id", "messages", "reply", "platform", "kind"}


# --- D1/D2: log_sandbox_exec ---


def test_log_sandbox_exec_writes_required_fields(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_sandbox_exec(elapsed_s=1.23456, exit_code=0, stdout_bytes=42, stderr_bytes=7)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["kind"] == "sandbox_exec"
    assert entry["elapsed_s"] == 1.235
    assert entry["exit_code"] == 0
    assert entry["stdout_bytes"] == 42
    assert entry["stderr_bytes"] == 7
    assert "ts" in entry


def test_log_sandbox_exec_optional_fields_omitted_when_none(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_sandbox_exec(elapsed_s=0.5, exit_code=0, stdout_bytes=1, stderr_bytes=0)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert "sandbox_scope" not in entry
    assert "agent_name" not in entry
    assert "user_id" not in entry


def test_log_sandbox_exec_optional_fields_written_when_present(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_sandbox_exec(
        elapsed_s=0.5,
        exit_code=1,
        stdout_bytes=10,
        stderr_bytes=20,
        sandbox_scope="session",
        agent_name="support-bot",
        user_id="u-7",
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    assert entry["sandbox_scope"] == "session"
    assert entry["agent_name"] == "support-bot"
    assert entry["user_id"] == "u-7"


def test_log_sandbox_exec_records_only_metadata_not_content(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_sandbox_exec(elapsed_s=0.5, exit_code=0, stdout_bytes=999, stderr_bytes=5)
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip())
    # Only size metadata — never raw code, stdout, or stderr text.
    assert "stdout" not in entry
    assert "stderr" not in entry
    assert "code" not in entry
    assert set(entry) == {"ts", "kind", "elapsed_s", "exit_code", "stdout_bytes", "stderr_bytes"}


def test_serialize_image_block_replaced_with_placeholder():
    import base64

    from fleetent.eval_logger import _serialize

    raw = b"x" * 5000
    b64 = base64.b64encode(raw).decode("ascii")
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "see this"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }
    out = _serialize(msg)
    serialized = str(out)
    assert b64 not in serialized
    # Placeholder records mime and byte size.
    assert "image/png" in serialized
    assert str(len(raw)) in serialized
    # Text block survives untouched.
    text_blocks = [b for b in out["content"] if b.get("type") == "text"]
    assert any(b["text"] == "see this" for b in text_blocks)


def _assistant_tool_call_msg(arguments: str):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "fetch", "arguments": arguments},
            }
        ],
    }


def test_serialize_redacts_sensitive_tool_call_arg():
    import json as _json

    from fleetent.eval_logger import REDACTED_PLACEHOLDER, _serialize

    msg = _assistant_tool_call_msg('{"api_key": "sk-secret", "password": "hunter2"}')
    out = _serialize(msg)
    args = _json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert args["api_key"] == REDACTED_PLACEHOLDER
    assert args["password"] == REDACTED_PLACEHOLDER
    assert "sk-secret" not in str(out)
    assert "hunter2" not in str(out)


def test_serialize_keeps_nonsensitive_tool_call_arg():
    import json as _json

    from fleetent.eval_logger import _serialize

    msg = _assistant_tool_call_msg('{"query": "weather", "path": "/tmp/x"}')
    out = _serialize(msg)
    args = _json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert args["query"] == "weather"
    assert args["path"] == "/tmp/x"


def test_serialize_mixed_sensitive_and_plain_tool_call_args():
    import json as _json

    from fleetent.eval_logger import REDACTED_PLACEHOLDER, _serialize

    msg = _assistant_tool_call_msg('{"api_key": "sk-secret", "query": "weather"}')
    out = _serialize(msg)
    args = _json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert args["api_key"] == REDACTED_PLACEHOLDER
    assert args["query"] == "weather"


def test_serialize_message_without_tool_calls_unchanged():
    from fleetent.eval_logger import _serialize

    msg = {"role": "user", "content": "just text"}
    assert _serialize(msg) == {"role": "user", "content": "just text"}


def test_serialize_invalid_json_arguments_degrades_without_raising():
    from fleetent.eval_logger import _serialize

    msg = _assistant_tool_call_msg("not valid json {{{")
    out = _serialize(msg)
    # Unparseable arguments degrade to existing behavior: left as-is, no raise.
    assert out["tool_calls"][0]["function"]["arguments"] == "not valid json {{{"


def test_serialize_does_not_mutate_original_tool_call_msg():
    msg = _assistant_tool_call_msg('{"api_key": "sk-secret"}')
    from fleetent.eval_logger import _serialize

    _serialize(msg)
    # Original object keeps the plaintext value — runtime context untouched.
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"api_key": "sk-secret"}'


def test_serialize_reuses_sandbox_secrets_rule(monkeypatch):
    import json as _json

    import fleetent.integrations.sandbox.secrets as ss
    from fleetent.eval_logger import REDACTED_PLACEHOLDER, _serialize

    # A name not normally sensitive becomes sensitive once the shared rule is
    # extended at the single source of truth (sandbox_secrets), proving reuse.
    monkeypatch.setattr(ss, "SENSITIVE_TOKENS", ("WIDGET",))
    msg = _assistant_tool_call_msg('{"widget_id": "leak-me", "api_key": "kept"}')
    out = _serialize(msg)
    args = _json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert args["widget_id"] == REDACTED_PLACEHOLDER
    # api_key no longer matches the patched rule, so it survives.
    assert args["api_key"] == "kept"


def test_serialize_name_only_does_not_scan_value():
    import json as _json

    from fleetent.eval_logger import _serialize

    # Known limitation (same as SB5): a benign-named param embedding a secret in
    # its VALUE is not redacted — only names are filtered, values never scanned.
    msg = _assistant_tool_call_msg('{"note": "my key is sk-deadbeef"}')
    out = _serialize(msg)
    args = _json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert args["note"] == "my key is sk-deadbeef"


async def test_session_persistence_keeps_plaintext_tool_call_args(tmp_path, monkeypatch):
    # Redaction lives only in the trace serialization path; session writes raw.
    import fleetent.session_mgr as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    msg = _assistant_tool_call_msg('{"api_key": "sk-secret"}')
    await sm.save("sess-1", [msg])
    loaded = await sm.load("sess-1")
    assert loaded[0]["tool_calls"][0]["function"]["arguments"] == '{"api_key": "sk-secret"}'


# ── log_compression (AR16) ───────────────────────────────────────────────────


def test_log_compression_writes_kind_and_fields(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_compression(
        trigger="manual",
        outcome="summarized",
        tokens_before=1000,
        tokens_after=300,
        messages_before=20,
        messages_after=5,
        head_count=2,
        tail_count=2,
        dropped_count=16,
        elapsed_s=0.12,
        summary_model="gpt-x",
        summary_fingerprint="abc123",
        summary_len=240,
        session_id="sess-9",
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip().splitlines()[-1])
    assert entry["kind"] == "compression"
    assert entry["trigger"] == "manual"
    assert entry["outcome"] == "summarized"
    assert entry["tokens_before"] == 1000 and entry["tokens_after"] == 300
    assert entry["dropped_count"] == 16
    assert entry["summary_model"] == "gpt-x"
    assert entry["summary_fingerprint"] == "abc123"
    assert entry["session_id"] == "sess-9"


def test_log_compression_optional_fields_omitted_when_none(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_compression(
        trigger="tmax",
        outcome="degraded",
        tokens_before=900,
        tokens_after=400,
        messages_before=15,
        messages_after=4,
        head_count=2,
        tail_count=2,
        dropped_count=11,
        elapsed_s=0.05,
    )
    entry = json.loads((tmp_path / "traces.jsonl").read_text().strip().splitlines()[-1])
    for f in ("summary_model", "summary_fingerprint", "summary_len", "session_id", "user_id"):
        assert f not in entry


def test_log_compression_never_records_summary_body(tmp_path, monkeypatch):
    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    secret = "SECRET SUMMARY BODY do not log"
    el.log_compression(
        trigger="tmax",
        outcome="summarized",
        tokens_before=10,
        tokens_after=5,
        messages_before=3,
        messages_after=2,
        head_count=1,
        tail_count=1,
        dropped_count=1,
        elapsed_s=0.01,
        summary_fingerprint="ff00",
        summary_len=len(secret),
    )
    raw = (tmp_path / "traces.jsonl").read_text()
    assert secret not in raw  # only fingerprint + length, never the body


def test_log_run_sets_secrets_redacted_flag(tmp_path, monkeypatch):
    import json as _json

    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("in", "out", [_assistant_tool_call_msg('{"api_key": "sk-x"}')], 0.1)
    entry = _json.loads((tmp_path / "traces.jsonl").read_text().strip().splitlines()[-1])
    assert entry["secrets_redacted"] is True  # audit marker: a sensitive arg was redacted


def test_log_run_no_secrets_redacted_field_when_clean(tmp_path, monkeypatch):
    import json as _json

    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log_run("in", "out", [_assistant_tool_call_msg('{"query": "hi"}')], 0.1)
    entry = _json.loads((tmp_path / "traces.jsonl").read_text().strip().splitlines()[-1])
    assert "secrets_redacted" not in entry  # omitted when nothing was redacted


def test_log_sets_secrets_redacted_flag(tmp_path, monkeypatch):
    import json as _json

    import fleetent.eval_logger as el

    monkeypatch.setattr(el, "TRACE_PATH", tmp_path / "traces.jsonl")
    el.log("u1", [_assistant_tool_call_msg('{"password": "p"}')], "resp")
    entry = _json.loads((tmp_path / "traces.jsonl").read_text().strip().splitlines()[-1])
    assert entry["secrets_redacted"] is True
