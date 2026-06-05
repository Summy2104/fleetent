import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent.intelligence.memory import extraction
from tests.evaluation.memory_extraction_eval import (
    _REAL_LLM_API_KEY_ENV,
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
    monkeypatch.delenv(_REAL_LLM_API_KEY_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_llm_fixture(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_llm_evaluation_treats_default_test_key_as_missing(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.setenv(_REAL_LLM_API_KEY_ENV, "test-key")

    def should_skip_before_client(**kwargs):
        raise AssertionError("real LLM evaluation should skip before client creation")

    monkeypatch.setattr(extraction, "AsyncOpenAI", should_skip_before_client)

    with pytest.raises(pytest.skip.Exception) as exc_info:
        await run_real_llm_fixture(load_fixtures()[0], tmp_path, monkeypatch)

    assert "real provider credential" in str(exc_info.value)


async def test_real_llm_evaluation_skips_when_credentials_do_not_match_memory_route(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.delenv(_REAL_LLM_API_KEY_ENV, raising=False)

    def should_skip_before_client(**kwargs):
        raise AssertionError("real LLM evaluation should skip before client creation")

    monkeypatch.setattr(extraction, "AsyncOpenAI", should_skip_before_client)

    with pytest.raises(pytest.skip.Exception) as exc_info:
        await run_real_llm_fixture(load_fixtures()[0], tmp_path, monkeypatch)

    assert "real provider credential" in str(exc_info.value)


async def test_real_llm_evaluation_accepts_configured_memory_route_api_key_env(
    tmp_path, monkeypatch
) -> None:
    fixture = load_fixtures()[0]
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.setenv(_REAL_LLM_API_KEY_ENV, "real-memory-route-key")
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

    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **kwargs: client)

    try:
        result = await run_real_llm_fixture(fixture, tmp_path, monkeypatch)
    except pytest.skip.Exception as exc:
        pytest.fail(f"configured memory route credential should not skip: {exc}")

    assert result.llm_route_names == ["memory_extraction"]


def test_default_required_env_preserves_real_llm_operator_credentials(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "_fleetent_root_conftest", Path(__file__).resolve().parents[1] / "conftest.py"
    )
    assert spec is not None
    assert spec.loader is not None
    root_conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_conftest)
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.setenv(_REAL_LLM_API_KEY_ENV, "real-provider-key")
    recorded_setenv: list[tuple[str, str]] = []

    class RecordingMonkeyPatch:
        def setenv(self, key: str, value: str) -> None:
            recorded_setenv.append((key, value))
            os.environ[key] = value

    root_conftest._default_required_env.__wrapped__(RecordingMonkeyPatch())

    assert os.environ[_REAL_LLM_API_KEY_ENV] == "real-provider-key"
    assert (_REAL_LLM_API_KEY_ENV, "test-key") not in recorded_setenv


async def test_real_llm_evaluation_uses_memory_extraction_route_when_enabled(
    tmp_path, monkeypatch
) -> None:
    fixture = load_fixtures()[0]
    monkeypatch.setenv("FLEETENT_EVAL_REAL_LLM", "1")
    monkeypatch.setenv(_REAL_LLM_API_KEY_ENV, "real-provider-key")
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

    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **kwargs: client)

    result = await run_real_llm_fixture(fixture, tmp_path, monkeypatch)

    assert result.llm_route_names == ["memory_extraction"]


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_real_llm_memory_extraction_fixture(fixture, tmp_path, monkeypatch) -> None:
    result = await run_real_llm_fixture(fixture, tmp_path, monkeypatch)

    assert_fixture_memory_state(result.rows, fixture)
