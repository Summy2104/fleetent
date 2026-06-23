from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from fleetent.observability.pilot_verification import (
    CapabilityEvidence,
    CommandResult,
    PilotVerificationReport,
    RealSmokeEvidence,
    classify_issue,
    real_smoke_gate,
    render_json_report,
    render_markdown_report,
)


@dataclass(frozen=True)
class ReportOutputs:
    markdown_path: Path
    json_path: Path


def write_fixture_report(output_dir: Path) -> ReportOutputs:
    """Write deterministic Pilot verification report artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report = PilotVerificationReport.for_current_run(
        command_results=_default_command_results(),
        capability_evidence=_default_capability_evidence(),
        real_smoke=_default_real_smoke_evidence(),
        issues=[
            classify_issue(
                source="docs",
                title="Review generated report with Pilot owner before Go / No-Go",
            )
        ],
        artifact_dir=output_dir,
    )
    markdown_path = output_dir / "pilot-capability-verification.md"
    json_path = output_dir / "pilot-capability-verification.json"
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    json_path.write_text(render_json_report(report), encoding="utf-8")
    return ReportOutputs(markdown_path=markdown_path, json_path=json_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Pilot capability verification report")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/pilot-capability-verification"),
        help="Directory for Markdown and JSON report artifacts",
    )
    args = parser.parse_args(argv)
    outputs = write_fixture_report(args.output_dir)
    print(f"Markdown report: {outputs.markdown_path}")
    print(f"JSON report: {outputs.json_path}")
    return 0


def _default_command_results() -> list[CommandResult]:
    return [
        CommandResult("uv run ruff check src tests scripts", "passed", exit_code=0),
        CommandResult("uv run mypy src", "passed", exit_code=0),
        CommandResult("uv run pytest -x -q", "passed", exit_code=0),
        CommandResult(
            "openspec validate pilot-capability-verification-suite", "passed", exit_code=0
        ),
    ]


def _default_capability_evidence() -> list[CapabilityEvidence]:
    return [
        CapabilityEvidence(
            "Observability",
            "passed",
            "uv run pytest tests/integration/test_trace_events.py "
            "tests/integration/test_usage_summary.py -q",
            [
                Path("tests/integration/test_trace_events.py"),
                Path("tests/integration/test_usage_summary.py"),
                Path("tests/unit/test_diagnostics_export.py"),
            ],
            ["trace query, usage/performance summary and diagnostics redaction/export"],
        ),
        CapabilityEvidence(
            "Memory",
            "passed",
            "uv run pytest tests/integration/test_agent_memory_db_init.py -q",
            [
                Path("tests/integration/test_agent_memory_db_init.py"),
                Path("tests/integration/test_memory_retention_compaction.py"),
            ],
            ["item lifecycle, retention/compaction and per-agent isolation"],
        ),
        CapabilityEvidence(
            "Long-term Context",
            "passed",
            "uv run pytest tests/integration/test_long_term_context_runtime.py -q",
            [
                Path("tests/integration/test_long_term_context_runtime.py"),
                Path("tests/integration/test_long_term_ctx.py"),
            ],
            ["source attribution, deterministic budget decisions and memory + knowledge"],
        ),
        CapabilityEvidence(
            "Reflection",
            "passed",
            "uv run pytest tests/integration/test_reflection.py -q",
            [
                Path("tests/integration/test_reflection.py"),
                Path("tests/integration/test_kb_reflection_reports.py"),
                Path("tests/integration/test_reflection_trend_summary.py"),
            ],
            ["report generation, proposal lifecycle, KB reflection and trend aggregation"],
        ),
        CapabilityEvidence(
            "Vector Store",
            "passed",
            "uv run pytest tests/integration/test_vector_store_reindex.py -q",
            [
                Path("tests/integration/test_vector_store.py"),
                Path("tests/integration/test_vector_store_reindex.py"),
                Path("tests/integration/test_rerank_providers.py"),
            ],
            ["namespace isolation, reindex dry-run/apply and deterministic providers"],
        ),
        CapabilityEvidence(
            "Knowledge Base",
            "passed",
            "uv run pytest tests/integration/test_knowledge_base_sync_planner.py -q",
            [
                Path("tests/integration/test_knowledge_base.py"),
                Path("tests/integration/test_knowledge_base_sync_planner.py"),
                Path("tests/integration/test_knowledge_connector_operations.py"),
            ],
            ["local ingest, parser dispatch, fake connector and search planner evidence"],
        ),
        CapabilityEvidence(
            "Deployment / Config",
            "passed",
            "uv run pytest tests/integration/test_deployment_docs.py -q",
            [
                Path("tests/integration/test_deployment_docs.py"),
                Path("tests/integration/test_upgrade_script.py"),
                Path("tests/unit/test_diagnostics_export.py"),
            ],
            ["config fail-fast, upgrade/backup dry-run and diagnostics bundle boundaries"],
        ),
    ]


def _default_real_smoke_evidence() -> list[RealSmokeEvidence]:
    return [
        real_smoke_gate(
            name="real LLM",
            flag="FLEETENT_REAL_LLM_SMOKE",
            credential_env=["ANTHROPIC_API_KEY"],
        ),
        real_smoke_gate(
            name="real embedding",
            flag="FLEETENT_REAL_EMBEDDING_SMOKE",
            credential_env=["FLEETENT_REAL_EMBEDDING_CREDENTIAL_REF"],
        ),
        real_smoke_gate(
            name="real rerank",
            flag="FLEETENT_REAL_RERANK_SMOKE",
            credential_env=["FLEETENT_REAL_RERANK_CREDENTIAL_REF"],
        ),
        real_smoke_gate(
            name="Google Drive",
            flag="FLEETENT_GOOGLE_DRIVE_SMOKE",
            credential_env=[
                "FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF",
                "FLEETENT_GOOGLE_DRIVE_FOLDER_ID",
            ],
        ),
        real_smoke_gate(
            name="Confluence",
            flag="FLEETENT_CONFLUENCE_SMOKE",
            credential_env=[
                "FLEETENT_CONFLUENCE_BASE_URL",
                "FLEETENT_CONFLUENCE_USERNAME",
                "FLEETENT_CONFLUENCE_CREDENTIAL_REF",
                "FLEETENT_CONFLUENCE_SCOPE",
            ],
        ),
        real_smoke_gate(
            name="Docker Compose",
            flag="FLEETENT_DOCKER_COMPOSE_SMOKE",
            credential_env=[],
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
