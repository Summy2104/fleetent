from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import memory_layer
from tests.evaluation.memory_extraction_eval import (
    REQUIRED_FIXTURE_FIELDS,
    FixtureValidationError,
    assert_fixture_memory_state,
    load_fixtures,
    memory_rows,
    run_mock_fixture,
    run_real_llm_fixture,
    validate_fixture,
)


def test_fixture_validation_requires_explicit_schema_fields() -> None:
    fixture = {
        "name": "identity create",
        "initial_memories": [],
        "conversation": [{"role": "user", "content": "I am a backend engineer."}],
        "mock_actions": [
            {"action": "create", "type": "identity", "content": "User is a backend engineer"}
        ],
        "expected_memories": [{"type": "identity", "content": "User is a backend engineer"}],
        "forbidden_memories": [],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "identity create",
        "initial_memories": [],
        "conversation": [{"role": "user", "content": "I am a backend engineer."}],
        "mock_actions": [
            {"action": "create", "type": "identity", "content": "User is a backend engineer"}
        ],
        "expected_memories": [{"type": "identity", "content": "User is a backend engineer"}],
        "forbidden_memories": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_validation_rejects_illegal_action_type() -> None:
    fixture = {
        "name": "invalid action",
        "initial_memories": [],
        "conversation": [{"role": "user", "content": "I am a backend engineer."}],
        "mock_actions": [
            {"action": "archive", "type": "identity", "content": "User is a backend engineer"}
        ],
        "expected_memories": [],
        "forbidden_memories": [],
    }

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_loader_returns_required_memory_extraction_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "identity create",
        "identity update",
        "context update with ttl refresh",
        "preferences create",
        "one-off preference request ignore",
        "explicit forget delete",
        "noisy invalid conversation ignore",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


async def test_mock_actions_drive_extract_and_update_expected_memory_state(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "identity create",
        "initial_memories": [],
        "conversation": [{"role": "user", "content": "I am a backend engineer."}],
        "mock_actions": [
            {"action": "create", "type": "identity", "content": "User is a backend engineer"}
        ],
        "expected_memories": [{"type": "identity", "content": "User is a backend engineer"}],
        "forbidden_memories": [],
    }

    result = await run_mock_fixture(fixture, tmp_path, monkeypatch)

    assert_fixture_memory_state(result.rows, fixture)
    assert result.llm_route_names == ["memory_extraction"]


async def test_forbidden_memories_are_rejected_after_fixture_run(tmp_path, monkeypatch) -> None:
    fixture = {
        "name": "one-off preference ignore",
        "initial_memories": [],
        "conversation": [{"role": "user", "content": "Use bullet points for this answer."}],
        "mock_actions": [{"action": "ignore", "reason": "one-off formatting request"}],
        "expected_memories": [],
        "forbidden_memories": [{"type": "preferences", "content": "User prefers bullet points"}],
    }

    result = await run_mock_fixture(fixture, tmp_path, monkeypatch)

    assert_fixture_memory_state(result.rows, fixture)


async def test_mock_runner_isolates_model_router_vector_store_and_sqlite(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "isolated dependencies",
        "initial_memories": [
            {
                "id": "mem-existing",
                "type": "identity",
                "content": "User is a backend engineer",
            }
        ],
        "conversation": [{"role": "user", "content": "Actually, I am a platform engineer."}],
        "mock_actions": [
            {
                "action": "update",
                "target_id": "mem-existing",
                "type": "identity",
                "content": "User is a platform engineer",
            }
        ],
        "expected_memories": [{"type": "identity", "content": "User is a platform engineer"}],
        "forbidden_memories": [{"type": "identity", "content": "User is a backend engineer"}],
    }

    result = await run_mock_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path == tmp_path / "memory-extraction-eval.db"
    assert result.vector_upserts == [
        ("mem-existing", "User is a platform engineer", "mem:evaluation-user")
    ]
    assert result.vector_deletes == []
    assert memory_rows(result.db_path) == result.rows
    assert_fixture_memory_state(result.rows, fixture)


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_memory_extraction_fixture_final_state(fixture, tmp_path, monkeypatch) -> None:
    result = await run_mock_fixture(fixture, tmp_path, monkeypatch)

    assert_fixture_memory_state(result.rows, fixture)


async def test_real_llm_evaluation_skips_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_LLM", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_llm_fixture(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_llm_evaluation_skips_without_provider_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    for env_name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_llm_fixture(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_llm_evaluation_uses_memory_extraction_route_when_enabled(
    tmp_path, monkeypatch
) -> None:
    fixture = load_fixtures()[0]
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    route_names: list[str] = []
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='[{"action": "ignore", "reason": "test"}]')
                )
            ]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    cfg = SimpleNamespace(model="real-route-test", max_tokens=256)

    def get_client(route_name: str):
        route_names.append(route_name)
        return client, cfg

    monkeypatch.setattr(memory_layer, "get_async_client_and_config", get_client)

    result = await run_real_llm_fixture(fixture, tmp_path, monkeypatch)

    assert result.llm_route_names == ["memory_extraction"]
    assert route_names == ["memory_extraction"]


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_real_llm_memory_extraction_fixture(fixture, tmp_path, monkeypatch) -> None:
    result = await run_real_llm_fixture(fixture, tmp_path, monkeypatch)

    assert_fixture_memory_state(result.rows, fixture)
