import pytest

from tests.evaluation.reflection_report_eval import (
    REQUIRED_FIXTURE_FIELDS,
    FixtureValidationError,
    assert_finding_expectations,
    load_fixtures,
    run_deterministic_fixture,
    run_real_route_smoke,
    validate_fixture,
)


def test_fixture_validation_requires_explicit_schema_fields() -> None:
    fixture = {
        "name": "memory candidate",
        "scope": "user-1",
        "trace_events": [
            {
                "id": "trace-1",
                "run_id": "run-1",
                "event_type": "agent_run_completed",
                "payload": {"memory_fact": "User prefers Python"},
                "user_id": "user-1",
            }
        ],
        "memory_signals": [],
        "expected_findings": [
            {
                "type": "memory_candidate",
                "summary_contains": "User prefers Python",
                "evidence_ids": ["trace-1", "trace-2"],
                "metadata": {"fact": "User prefers Python"},
            }
        ],
        "forbidden_findings": [{"type": "memory_conflict"}],
        "forbidden_persisted_text": ["raw private transcript"],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "memory candidate",
        "scope": "user-1",
        "trace_events": [],
        "memory_signals": [],
        "expected_findings": [],
        "forbidden_findings": [],
        "forbidden_persisted_text": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_validation_rejects_malformed_finding_assertions() -> None:
    fixture = {
        "name": "malformed finding assertion",
        "scope": "user-1",
        "trace_events": [],
        "memory_signals": [],
        "expected_findings": [{"summary_contains": "missing type"}],
        "forbidden_findings": [],
        "forbidden_persisted_text": [],
    }

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_loader_returns_required_reflection_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "memory candidate finding",
        "memory conflict finding",
        "skill opportunity finding",
        "noisy traces produce no findings",
        "persisted report redacts transcript",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


async def test_runner_patches_observability_and_memory_public_apis(tmp_path, monkeypatch) -> None:
    fixture = {
        "name": "memory candidate",
        "scope": "user-1",
        "trace_events": [
            {
                "id": "trace-1",
                "run_id": "run-1",
                "event_type": "agent_run_completed",
                "payload": {"memory_fact": "User prefers Python"},
                "user_id": "user-1",
            },
            {
                "id": "trace-2",
                "run_id": "run-2",
                "event_type": "agent_run_completed",
                "payload": {"memory_fact": "User prefers Python"},
                "user_id": "user-1",
            },
        ],
        "memory_signals": [],
        "expected_findings": [
            {
                "type": "memory_candidate",
                "summary_contains": "User prefers Python",
                "evidence_ids": ["trace-1", "trace-2"],
                "metadata": {"fact": "User prefers Python"},
            }
        ],
        "forbidden_findings": [{"type": "memory_conflict"}],
        "forbidden_persisted_text": ["raw private transcript"],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path == tmp_path / "reflection-report-eval.db"
    assert result.trace_query_user_ids == ["user-1"]
    assert result.memory_queries[0][0] == "user-1"
    assert_finding_expectations(result)


async def test_runner_rejects_forbidden_findings(tmp_path, monkeypatch) -> None:
    fixture = {
        "name": "forbidden finding failure",
        "scope": "user-1",
        "trace_events": [
            {
                "id": "trace-1",
                "run_id": "run-1",
                "event_type": "agent_run_completed",
                "payload": {"task_pattern": "summarize Jira progress"},
                "user_id": "user-1",
            },
            {
                "id": "trace-2",
                "run_id": "run-2",
                "event_type": "agent_run_completed",
                "payload": {"task_pattern": "summarize Jira progress"},
                "user_id": "user-1",
            },
        ],
        "memory_signals": [],
        "expected_findings": [],
        "forbidden_findings": [
            {"type": "skill_opportunity", "summary_contains": "summarize Jira progress"}
        ],
        "forbidden_persisted_text": [],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    with pytest.raises(AssertionError, match="forbidden finding found"):
        assert_finding_expectations(result)


async def test_runner_validates_persisted_payload_redaction(tmp_path, monkeypatch) -> None:
    raw_user_input = "raw private transcript"
    fixture = {
        "name": "persisted redaction",
        "scope": "user-1",
        "trace_events": [
            {
                "id": "trace-1",
                "run_id": "run-1",
                "event_type": "agent_run_completed",
                "payload": {
                    "user_input": raw_user_input,
                    "memory_fact": "User prefers Python",
                },
                "user_id": "user-1",
            },
            {
                "id": "trace-2",
                "run_id": "run-2",
                "event_type": "agent_run_completed",
                "payload": {
                    "user_input": raw_user_input,
                    "memory_fact": "User prefers Python",
                },
                "user_id": "user-1",
            },
        ],
        "memory_signals": [],
        "expected_findings": [{"type": "memory_candidate"}],
        "forbidden_findings": [],
        "forbidden_persisted_text": [raw_user_input],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.persisted_findings_json
    assert_finding_expectations(result)


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fixture: fixture["name"])
async def test_reflection_report_fixture_expectations(fixture, tmp_path, monkeypatch) -> None:
    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert_finding_expectations(result)


async def test_real_route_smoke_skips_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_REFLECTION", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_route_smoke(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_route_smoke_skips_without_explicit_local_fixture_config(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_REFLECTION", "1")
    monkeypatch.delenv("FLEETENT_EVAL_REFLECTION_FIXTURE", raising=False)

    with pytest.raises(pytest.skip.Exception):
        await run_real_route_smoke(load_fixtures()[0], tmp_path, monkeypatch)
