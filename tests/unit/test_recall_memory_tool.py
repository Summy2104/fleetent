"""Unit tests: recall_memory agent tool — full memory enumeration."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fleetent.memory.facts_models import Fact


def _fact(subject: str, relation: str, obj: str, statement: str | None = None) -> Fact:
    now = datetime.now(UTC)
    return Fact(
        fact_id=f"{subject}-{relation}-{obj}",
        user_id="u1",
        subject=subject,
        relation=relation,
        object=obj,
        cardinality="multi",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
        statement=statement,
    )


def _ctx(user_id: str | None):
    principal = SimpleNamespace(user_id=user_id) if user_id else None
    return SimpleNamespace(principal=principal)


async def test_recall_lists_all_subjects(monkeypatch) -> None:
    from fleetent.tools import builtin_tools

    facts = [
        _fact("user", "name", "Xin", statement="用户的名字是 Xin"),
        _fact("agent", "name", "fleetent", statement="助手叫 fleetent"),
        _fact("张三", "works_at", "Acme", statement="张三在 Acme 工作"),
    ]
    captured = {}

    def _list(user_id, subject=None):
        captured["user_id"] = user_id
        captured["subject"] = subject
        return facts

    monkeypatch.setattr(builtin_tools.memory, "list_active_facts", _list)

    out = await builtin_tools.recall_memory(tool_context=_ctx("u1"))
    assert captured["user_id"] == "u1"
    assert captured["subject"] is None
    # all three statements appear
    assert "用户的名字是 Xin" in out
    assert "助手叫 fleetent" in out
    assert "张三在 Acme 工作" in out


async def test_recall_subject_filter(monkeypatch) -> None:
    from fleetent.tools import builtin_tools

    captured = {}

    def _list(user_id, subject=None):
        captured["subject"] = subject
        return [_fact("张三", "works_at", "Acme", statement="张三在 Acme")]

    monkeypatch.setattr(builtin_tools.memory, "list_active_facts", _list)

    out = await builtin_tools.recall_memory(subject="张三", tool_context=_ctx("u1"))
    assert captured["subject"] == "张三"
    assert "张三在 Acme" in out


async def test_recall_no_principal_does_not_raise(monkeypatch) -> None:
    from fleetent.tools import builtin_tools

    # No principal → cannot resolve user → friendly text, no raise, no DB call.
    out = await builtin_tools.recall_memory(tool_context=_ctx(None))
    assert isinstance(out, str) and out  # non-empty explanatory text


async def test_recall_empty_memory(monkeypatch) -> None:
    from fleetent.tools import builtin_tools

    monkeypatch.setattr(builtin_tools.memory, "list_active_facts", lambda *a, **k: [])

    out = await builtin_tools.recall_memory(tool_context=_ctx("u1"))
    assert isinstance(out, str) and out  # "暂无记忆"-type message, not empty/raise


async def test_recall_falls_back_to_triple_when_no_statement(monkeypatch) -> None:
    from fleetent.tools import builtin_tools

    monkeypatch.setattr(
        builtin_tools.memory,
        "list_active_facts",
        lambda *a, **k: [_fact("user", "works_at", "Northstar", statement=None)],
    )

    out = await builtin_tools.recall_memory(tool_context=_ctx("u1"))
    # no statement → fall back to a subject relation: object rendering
    assert "works_at" in out and "Northstar" in out
