"""Unit tests: run_pipeline chains extract → resolve → classify → commit."""

from __future__ import annotations

from fleetent.memory.facts_models import ClassifiedFact, RawFact, ResolvedFact


class _FakeRelationStore:
    """Minimal stand-in for facts_store used by run_pipeline's known-relations fetch."""

    def list_relation_clusters(self):
        return []


async def test_run_pipeline_end_to_end(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    captured: dict[str, object] = {}

    async def _fake_extract(
        turn_content, llm_client, known_relations=None, user_aliases=None, active_facts=None
    ):
        return [RawFact(subject="user", relation="has_skill", object="Rust", temporal="none")]

    async def _fake_resolve(raw, store, llm_client):
        return ResolvedFact(
            subject=raw.subject,
            relation="has_skill",
            object=raw.object,
            temporal=raw.temporal,
            cardinality="multi",
        )

    async def _fake_classify(resolved, existing_facts, llm_client):
        return ClassifiedFact(
            subject=resolved.subject,
            relation=resolved.relation,
            object=resolved.object,
            temporal=resolved.temporal,
            cardinality=resolved.cardinality,
            verdict="Orthogonal",
        )

    def _fake_commit(user_id, classified, db, *, source_turn):
        captured["classified"] = classified
        captured["user_id"] = user_id
        return []

    async def _fake_sync(user_id, *, new_active, superseded_ids, vector_backend):
        captured["synced"] = True

    monkeypatch.setattr(facts_pipeline, "extract_facts", _fake_extract)
    monkeypatch.setattr(facts_pipeline, "resolve_relation", _fake_resolve)
    monkeypatch.setattr(facts_pipeline, "classify_relation", _fake_classify)
    monkeypatch.setattr(facts_pipeline, "_commit_facts", _fake_commit)
    monkeypatch.setattr(facts_pipeline, "_sync_vectors", _fake_sync)
    monkeypatch.setattr(facts_pipeline, "_active_facts_for_relation", lambda *a: [])
    monkeypatch.setattr(facts_pipeline, "_all_active_facts_for_user", lambda uid: [])
    monkeypatch.setattr(facts_pipeline, "_relation_store", lambda: _FakeRelationStore())
    monkeypatch.setattr(facts_pipeline, "_known_user_aliases", lambda uid: set())

    await facts_pipeline.run_pipeline(
        user_id="u1",
        turn_content="I use Rust",
        db=object(),
        vector_backend=object(),
        llm_client=object(),
        source_turn="t1",
    )

    classified = captured["classified"]
    assert len(classified) == 1  # type: ignore[arg-type]
    assert classified[0].verdict == "Orthogonal"  # type: ignore[index]
    assert captured["user_id"] == "u1"


async def test_run_pipeline_no_facts_skips_commit(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    called = {"commit": False}

    async def _fake_extract(
        turn_content, llm_client, known_relations=None, user_aliases=None, active_facts=None
    ):
        return []

    def _fake_commit(user_id, classified, db, *, source_turn):
        called["commit"] = True
        return []

    monkeypatch.setattr(facts_pipeline, "extract_facts", _fake_extract)
    monkeypatch.setattr(facts_pipeline, "_commit_facts", _fake_commit)
    monkeypatch.setattr(facts_pipeline, "_all_active_facts_for_user", lambda uid: [])
    monkeypatch.setattr(facts_pipeline, "_relation_store", lambda: _FakeRelationStore())
    monkeypatch.setattr(facts_pipeline, "_known_user_aliases", lambda uid: set())

    await facts_pipeline.run_pipeline(
        user_id="u1",
        turn_content="hi",
        db=object(),
        vector_backend=object(),
        llm_client=object(),
        source_turn="t1",
    )
    assert called["commit"] is False


async def test_run_pipeline_logs_input_for_diagnosis(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    logged = {}

    async def _fake_extract(
        turn_content, llm_client, known_relations=None, user_aliases=None, active_facts=None
    ):
        return []  # 0 facts — the case we need to diagnose

    class _Slog:
        def info(self, event, **fields):
            if event == "facts_extracted":
                logged.update(fields)

    monkeypatch.setattr(facts_pipeline, "extract_facts", _fake_extract)
    monkeypatch.setattr(facts_pipeline, "_all_active_facts_for_user", lambda uid: [])
    monkeypatch.setattr(facts_pipeline, "_relation_store", lambda: _FakeRelationStore())
    monkeypatch.setattr(facts_pipeline, "_known_user_aliases", lambda uid: set())
    monkeypatch.setattr(facts_pipeline, "slog", _Slog())

    await facts_pipeline.run_pipeline(
        user_id="u1",
        turn_content="我刚换了一家新公司",
        db=object(),
        vector_backend=object(),
        llm_client=object(),
        source_turn="t1",
    )
    # The input must be logged so a 0-fact extraction is auditable.
    assert logged.get("input") == "我刚换了一家新公司"
    assert logged.get("count") == 0
