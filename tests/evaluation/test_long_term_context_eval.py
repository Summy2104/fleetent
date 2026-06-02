import pytest

from tests.evaluation.long_term_context_eval import (
    REQUIRED_FIXTURE_FIELDS,
    FixtureValidationError,
    assert_context_expectations,
    load_fixtures,
    run_deterministic_fixture,
    run_real_provider_smoke,
    validate_fixture,
)


def test_fixture_validation_requires_explicit_schema_fields() -> None:
    fixture = {
        "name": "memory preference injection",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "How should you answer me?",
        "available_tokens": 300,
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers concise answers.",
            }
        ],
        "knowledge": [],
        "expected_text": ["User prefers concise answers."],
        "forbidden_text": ["Payroll incidents"],
        "expected_sources": [{"source_type": "memory", "source_id": "mem-1"}],
        "forbidden_sources": [{"source_type": "knowledge", "source_id": "kb-1"}],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "memory preference injection",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "How should you answer me?",
        "available_tokens": 300,
        "memories": [],
        "knowledge": [],
        "expected_text": [],
        "forbidden_text": [],
        "expected_sources": [],
        "forbidden_sources": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_validation_rejects_malformed_source_assertions() -> None:
    fixture = {
        "name": "malformed source assertion",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "How should you answer me?",
        "available_tokens": 300,
        "memories": [],
        "knowledge": [],
        "expected_text": [],
        "forbidden_text": [],
        "expected_sources": [{"source_id": "mem-1"}],
        "forbidden_sources": [],
    }

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_loader_returns_required_long_term_context_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "memory preference injection",
        "kb factual injection",
        "combined memory and knowledge injection",
        "insufficient budget omits knowledge",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


async def test_runner_patches_memory_provider_and_validates_expected_text(monkeypatch) -> None:
    fixture = {
        "name": "memory preference injection",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "How should you answer me?",
        "available_tokens": 300,
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers concise answers.",
            }
        ],
        "knowledge": [],
        "expected_text": ["User prefers concise answers."],
        "forbidden_text": ["Payroll incidents"],
        "expected_sources": [{"source_type": "memory", "source_id": "mem-1"}],
        "forbidden_sources": [{"source_type": "knowledge", "source_id": "kb-1"}],
    }

    result = await run_deterministic_fixture(fixture, monkeypatch)

    assert result.memory_queries == [("user-1", "How should you answer me?", 10)]
    assert result.knowledge_queries == [("user-1", "How should you answer me?", "agent-1", 10)]
    assert_context_expectations(result)


async def test_runner_patches_fake_knowledge_provider_and_validates_sources(monkeypatch) -> None:
    fixture = {
        "name": "kb factual injection",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "Who handles payroll incidents?",
        "available_tokens": 300,
        "memories": [],
        "knowledge": [
            {
                "id": "kb-1",
                "content": "Payroll incidents are escalated to HR operations.",
                "score": 0.9,
                "metadata": {"title": "Support handbook"},
            }
        ],
        "expected_text": ["Payroll incidents are escalated to HR operations."],
        "forbidden_text": ["User prefers concise answers."],
        "expected_sources": [{"source_type": "knowledge", "source_id": "kb-1"}],
        "forbidden_sources": [{"source_type": "memory", "source_id": "mem-1"}],
    }

    result = await run_deterministic_fixture(fixture, monkeypatch)

    assert result.memory_queries == [("user-1", "Who handles payroll incidents?", 10)]
    assert result.knowledge_queries == [("user-1", "Who handles payroll incidents?", "agent-1", 10)]
    assert_context_expectations(result)


async def test_runner_rejects_forbidden_text_and_sources(monkeypatch) -> None:
    fixture = {
        "name": "forbidden expectation failure",
        "user_id": "user-1",
        "agent_id": "agent-1",
        "query": "How should you answer me?",
        "available_tokens": 300,
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers concise answers.",
            }
        ],
        "knowledge": [],
        "expected_text": [],
        "forbidden_text": ["User prefers concise answers."],
        "expected_sources": [],
        "forbidden_sources": [{"source_type": "memory", "source_id": "mem-1"}],
    }

    result = await run_deterministic_fixture(fixture, monkeypatch)

    with pytest.raises(AssertionError, match="forbidden text found"):
        assert_context_expectations(result)


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_long_term_context_fixture_expectations(fixture, monkeypatch) -> None:
    result = await run_deterministic_fixture(fixture, monkeypatch)

    assert_context_expectations(result)


async def test_real_provider_smoke_skips_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_provider_smoke(load_fixtures()[0])


async def test_real_provider_smoke_skips_without_provider_config(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("FLEETENT_EVAL_EMBEDDING_API_KEY", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_provider_smoke(load_fixtures()[0])
