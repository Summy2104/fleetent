from pathlib import Path

import pytest

from tests.evaluation.knowledge_base_retrieval_eval import (
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
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Escalate payroll incidents to HR operations.",
            }
        ],
        "queries": [
            {
                "text": "Who handles payroll incidents?",
                "top_k": 3,
                "expected_chunks": ["payroll incidents"],
                "forbidden_chunks": ["database failover"],
            }
        ],
        "expected_chunks": ["payroll incidents"],
        "forbidden_chunks": ["database failover"],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Escalate payroll incidents to HR operations.",
            }
        ],
        "queries": [
            {
                "text": "Who handles payroll incidents?",
                "expected_chunks": ["payroll incidents"],
                "forbidden_chunks": [],
            }
        ],
        "expected_chunks": ["payroll incidents"],
        "forbidden_chunks": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_loader_returns_required_knowledge_base_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "support handbook vector retrieval",
        "tenant knowledge isolation",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


async def test_deterministic_runner_ingests_documents_and_validates_top_k(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "payroll.md",
                "content": "Payroll incidents require HR operations escalation.",
            },
            {
                "filename": "database.md",
                "content": "Database failover incidents require platform escalation.",
            },
        ],
        "queries": [
            {
                "text": "payroll incidents HR operations",
                "top_k": 1,
                "expected_chunks": ["Payroll incidents require HR operations escalation"],
                "forbidden_chunks": ["Database failover incidents"],
            }
        ],
        "expected_chunks": ["Payroll incidents require HR operations escalation"],
        "forbidden_chunks": ["Database failover incidents"],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path == tmp_path / "knowledge-base-retrieval-eval.db"
    assert result.vector_db_path == tmp_path / "knowledge-base-retrieval-vectors.db"
    assert result.document_count == 2
    assert result.query_results[0].query == "payroll incidents HR operations"
    assert_query_expectations(result.query_results[0])


async def test_forbidden_chunks_are_rejected_after_fixture_run(tmp_path, monkeypatch) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Payroll incidents require HR operations escalation.",
            }
        ],
        "queries": [
            {
                "text": "payroll incidents",
                "top_k": 1,
                "expected_chunks": ["Payroll incidents"],
                "forbidden_chunks": ["Payroll incidents"],
            }
        ],
        "expected_chunks": ["Payroll incidents"],
        "forbidden_chunks": ["Payroll incidents"],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    with pytest.raises(AssertionError, match="forbidden chunk found"):
        assert_query_expectations(result.query_results[0])


async def test_runner_isolates_sqlite_and_vector_store_from_data_dir(tmp_path, monkeypatch) -> None:
    fixture = load_fixtures()[0]
    data_db = Path("data/users.db").resolve()

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path.parent == tmp_path
    assert result.vector_db_path.parent == tmp_path
    assert result.db_path.resolve() != data_db
    assert result.vector_db_path.resolve() != data_db


async def test_real_embedding_evaluation_skips_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_EMBEDDING", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_embedding_evaluation_skips_without_provider_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_EMBEDDING", "1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "http://embedding.test/v1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.delenv("FLEETENT_EVAL_EMBEDDING_API_KEY", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_knowledge_base_retrieval_fixture_expectations(
    fixture, tmp_path, monkeypatch
) -> None:
    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    for query_result in result.query_results:
        assert_query_expectations(query_result)
