import pytest

from tests.evaluation.memory_kb_embedding_eval import (
    REQUIRED_FIXTURE_FIELDS,
    FixtureValidationError,
    assert_query_expectations,
    load_fixtures,
    run_deterministic_fixture,
    run_real_embedding_fixture,
    validate_fixture,
)


def test_fixture_validation_requires_explicit_schema_fields() -> None:
    fixture = {
        "name": "memory and kb retrieval",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers Python for backend services.",
            }
        ],
        "documents": [
            {
                "filename": "support.md",
                "content": "Payroll incidents are escalated to HR operations.",
            }
        ],
        "queries": [
            {
                "owner": "memory",
                "text": "backend language preference",
                "top_k": 3,
                "expected": ["Python for backend"],
                "forbidden": ["Payroll incidents"],
            }
        ],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "memory and kb retrieval",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [],
        "documents": [],
        "queries": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


@pytest.mark.parametrize("owner", ["agent", "", None])
def test_fixture_validation_rejects_unsupported_query_owner(owner) -> None:
    fixture = {
        "name": "invalid query owner",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [],
        "documents": [],
        "queries": [
            {
                "owner": owner,
                "text": "backend language preference",
                "top_k": 3,
                "expected": [],
                "forbidden": [],
            }
        ],
    }

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


@pytest.mark.parametrize("top_k", [0, -1, "3"])
def test_fixture_validation_rejects_invalid_top_k(top_k) -> None:
    fixture = {
        "name": "invalid top k",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [],
        "documents": [],
        "queries": [
            {
                "owner": "knowledge_base",
                "text": "payroll escalation",
                "top_k": top_k,
                "expected": [],
                "forbidden": [],
            }
        ],
    }

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


async def test_deterministic_runner_uses_tmp_databases_and_reindexes_both_owners(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "memory and kb retrieval",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers Python for backend services.",
            }
        ],
        "documents": [
            {
                "filename": "support.md",
                "content": "Payroll incidents are escalated to HR operations.",
            }
        ],
        "queries": [],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path == tmp_path / "memory-kb-embedding-eval.db"
    assert result.vector_db_path == tmp_path / "memory-kb-embedding-vectors.db"
    assert result.memory_reindex_summary.scanned == 1
    assert result.memory_reindex_summary.reindexed == 1
    assert result.kb_reindex_summary.scanned >= 1
    assert result.kb_reindex_summary.reindexed >= 1


async def test_memory_query_expectations_validate_expected_and_forbidden_snippets(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "memory retrieval",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [
            {
                "id": "mem-1",
                "type": "preferences",
                "content": "User prefers Python for backend services.",
            },
            {
                "id": "mem-2",
                "type": "context",
                "content": "User is planning a payroll migration.",
            },
        ],
        "documents": [],
        "queries": [
            {
                "owner": "memory",
                "text": "backend Python preference",
                "top_k": 1,
                "expected": ["Python for backend"],
                "forbidden": ["payroll migration"],
            }
        ],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert_query_expectations(result)


async def test_kb_query_expectations_validate_expected_and_forbidden_snippets(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "kb retrieval",
        "user_id": "user-1",
        "tenant_id": "default",
        "kb_id": "global",
        "memories": [],
        "documents": [
            {
                "filename": "support.md",
                "content": "Payroll incidents are escalated to HR operations.",
            },
            {
                "filename": "database.md",
                "content": "Database failover incidents go to platform engineering.",
            },
        ],
        "queries": [
            {
                "owner": "knowledge_base",
                "text": "payroll incidents HR operations",
                "top_k": 1,
                "expected": ["Payroll incidents"],
                "forbidden": ["Database failover"],
            }
        ],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert_query_expectations(result)


def test_fixture_loader_returns_required_combined_embedding_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "combined memory and knowledge embedding retrieval",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_combined_embedding_fixture_expectations(fixture, tmp_path, monkeypatch) -> None:
    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert_query_expectations(result)


async def test_real_embedding_evaluation_skips_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_EMBEDDING", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)


@pytest.mark.parametrize(
    "missing_env",
    [
        "FLEETENT_EVAL_EMBEDDING_ENDPOINT",
        "FLEETENT_EVAL_EMBEDDING_MODEL",
        "FLEETENT_EVAL_EMBEDDING_API_KEY",
        "FLEETENT_EVAL_EMBEDDING_DIMENSIONS",
    ],
)
async def test_real_embedding_evaluation_skips_without_complete_provider_config(
    missing_env: str, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_EMBEDDING", "1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "http://embedding.test/v1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_DIMENSIONS", "1024")
    monkeypatch.delenv(missing_env, raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)
