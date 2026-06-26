"""Unit tests: run_pipeline_from_conversation adapter (conversation + policy → pipeline)."""

from __future__ import annotations


async def test_adapter_builds_turn_text_and_delegates(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    captured: dict[str, object] = {}

    async def _fake_run_pipeline(
        *, user_id, turn_content, db, vector_backend, llm_client, source_turn
    ):
        captured["user_id"] = user_id
        captured["turn_content"] = turn_content
        captured["source_turn"] = source_turn

    monkeypatch.setattr(facts_pipeline, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(facts_pipeline, "_facts_db_and_backend", lambda: (object(), object()))
    monkeypatch.setattr(facts_pipeline, "_build_llm_client", lambda policy: object())

    conversation = [
        {"role": "user", "content": "I use Rust"},
        {"role": "assistant", "content": "Nice"},
    ]
    await facts_pipeline.run_pipeline_from_conversation(
        "u1", conversation, model_policy=None, source_turn="t1"
    )

    assert captured["user_id"] == "u1"
    assert "Rust" in captured["turn_content"]  # type: ignore[operator]
    assert captured["source_turn"] == "t1"


async def test_adapter_swallows_client_build_failure(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    def _boom(policy):
        raise RuntimeError("no model configured")

    monkeypatch.setattr(facts_pipeline, "_facts_db_and_backend", lambda: (object(), object()))
    monkeypatch.setattr(facts_pipeline, "_build_llm_client", _boom)

    # Best-effort: a client build failure must not propagate to the caller (loop).
    await facts_pipeline.run_pipeline_from_conversation(
        "u1", [{"role": "user", "content": "hi"}], model_policy=None, source_turn=None
    )


def test_conversation_to_text_only_includes_user_messages() -> None:
    from fleetent.memory import facts_pipeline

    # The agent reciting existing memories (assistant) must NOT feed extraction,
    # or recalled facts get re-extracted as "new" (the 张三 resurrection bug).
    conv = [
        {"role": "user", "content": "我叫 xin"},
        {"role": "assistant", "content": "你的记忆里有张三、李四、王五..."},
        {"role": "user", "content": "我在 Northstar 工作"},
    ]
    text = facts_pipeline._conversation_to_text(conv)
    assert "我叫 xin" in text
    assert "我在 Northstar 工作" in text
    # the agent's recital must be excluded
    assert "张三" not in text
    assert "李四" not in text
