from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

CapabilityStatus = Literal["passed", "failed", "skipped"]
IssueClassification = Literal["Pilot blocker", "Docs gap", "Enhancement", "Out-of-scope"]
Recommendation = Literal["Go", "Conditional Go", "No-Go"]
SmokeStatus = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class CommandResult:
    """Automated command result captured for Pilot verification."""

    command: str
    status: CapabilityStatus
    exit_code: int | None = None
    artifact: Path | None = None
    summary: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "artifact": str(self.artifact) if self.artifact else None,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class GateCommandResult(CommandResult):
    """Pilot gate command result with required/optional status and duration."""

    required: bool = True
    duration_seconds: float = 0.0

    def to_json(self) -> dict[str, object]:
        payload = super().to_json()
        payload["required"] = self.required
        payload["duration_seconds"] = self.duration_seconds
        return payload


@dataclass(frozen=True)
class ConfigValidationEvidence:
    status: str
    error_count: int
    skipped_count: int
    artifact: Path | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "artifact": str(self.artifact) if self.artifact else None,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "status": self.status,
        }


@dataclass(frozen=True)
class DiagnosticsEvidence:
    manifest_path: Path
    artifact_count: int

    def to_json(self) -> dict[str, object]:
        return {"artifact_count": self.artifact_count, "manifest_path": str(self.manifest_path)}


@dataclass(frozen=True)
class CapabilityEvidence:
    """Evidence for one owner capability domain."""

    capability: str
    status: CapabilityStatus
    command: str
    artifacts: list[Path]
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        missing = [path for path in self.artifacts if not path.exists()]
        if missing:
            paths = ", ".join(str(path) for path in missing)
            raise ValueError(f"capability evidence artifact does not exist: {paths}")

    def to_json(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "status": self.status,
            "command": self.command,
            "artifacts": [str(path) for path in self.artifacts],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class RealSmokeEvidence:
    """Opt-in real smoke status and skip reason."""

    name: str
    status: SmokeStatus
    missing_requirements: list[str] = field(default_factory=list)
    artifact: Path | None = None
    summary: str = ""

    @property
    def skip_reason(self) -> str | None:
        if self.status != "skipped":
            return None
        if self.missing_requirements:
            return "missing " + ", ".join(self.missing_requirements)
        return self.summary or "not enabled"

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "missing_requirements": list(self.missing_requirements),
            "skip_reason": self.skip_reason,
            "artifact": str(self.artifact) if self.artifact else None,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class PilotSmokeScenario:
    """Local/fake Pilot acceptance smoke evidence."""

    name: str
    evidence: dict[str, Any]
    required_evidence_keys: list[str]

    def missing_keys(self) -> list[str]:
        return [key for key in self.required_evidence_keys if key not in self.evidence]

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": "passed",
            "evidence": self.evidence,
            "required_evidence_keys": list(self.required_evidence_keys),
        }


@dataclass(frozen=True)
class VerificationIssue:
    """Issue classified by Pilot impact."""

    classification: IssueClassification
    title: str
    source: str
    detail: str = ""

    def to_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RunMetadata:
    """Metadata for one verification report run."""

    git_sha: str
    python_version: str
    generated_at: datetime
    artifact_dir: Path

    def to_json(self) -> dict[str, str]:
        return {
            "git_sha": self.git_sha,
            "python_version": self.python_version,
            "generated_at": self.generated_at.isoformat(),
            "artifact_dir": str(self.artifact_dir),
        }


@dataclass(frozen=True)
class PilotVerificationReport:
    """Human and machine-readable Pilot verification report."""

    metadata: RunMetadata
    command_results: list[CommandResult]
    capability_evidence: list[CapabilityEvidence]
    real_smoke: list[RealSmokeEvidence]
    issues: list[VerificationIssue]
    recommendation: Recommendation
    config_validation: ConfigValidationEvidence | None = None
    diagnostics: DiagnosticsEvidence | None = None
    connector_status: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def for_current_run(
        cls,
        *,
        command_results: list[CommandResult],
        capability_evidence: list[CapabilityEvidence],
        real_smoke: list[RealSmokeEvidence],
        issues: list[VerificationIssue],
        artifact_dir: Path,
        config_validation: ConfigValidationEvidence | None = None,
        diagnostics: DiagnosticsEvidence | None = None,
        connector_status: list[dict[str, object]] | None = None,
    ) -> PilotVerificationReport:
        """Build a report using current process and git metadata."""
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            metadata=RunMetadata(
                git_sha=_git_sha(),
                python_version=platform.python_version(),
                generated_at=datetime.now(UTC).replace(microsecond=0),
                artifact_dir=artifact_dir,
            ),
            command_results=command_results,
            capability_evidence=capability_evidence,
            real_smoke=real_smoke,
            issues=issues,
            recommendation=recommend(command_results, capability_evidence, real_smoke, issues),
            config_validation=config_validation,
            diagnostics=diagnostics,
            connector_status=connector_status or [],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "metadata": self.metadata.to_json(),
            "command_results": [item.to_json() for item in self.command_results],
            "capability_evidence": [item.to_json() for item in self.capability_evidence],
            "real_smoke": [item.to_json() for item in self.real_smoke],
            "issues": [item.to_json() for item in self.issues],
            "recommendation": self.recommendation,
            "config_validation": (
                self.config_validation.to_json() if self.config_validation else None
            ),
            "diagnostics": self.diagnostics.to_json() if self.diagnostics else None,
            "connector_status": list(self.connector_status),
        }


def classify_issue(*, source: str, title: str, detail: str = "") -> VerificationIssue:
    """Classify a verification issue using conservative Pilot impact rules."""
    source_lower = source.lower()
    title_lower = title.lower()
    text = f"{source_lower} {title_lower} {detail.lower()}"
    if "docs" in text or "documentation" in text:
        classification: IssueClassification = "Docs gap"
    elif "out-of-scope" in text or "out of scope" in text:
        classification = "Out-of-scope"
    elif "skip" in text or "enhancement" in text or "optional" in text:
        classification = "Enhancement"
    else:
        classification = "Pilot blocker"
    return VerificationIssue(
        classification=classification,
        title=title,
        source=source,
        detail=detail,
    )


def real_smoke_gate(
    *,
    name: str,
    flag: str,
    credential_env: list[str],
) -> RealSmokeEvidence:
    """Return skipped real-smoke evidence unless its flag and credentials are present."""
    missing = []
    if os.getenv(flag) != "1":
        missing.append(flag)
    missing.extend(name for name in credential_env if not os.getenv(name))
    if missing:
        return RealSmokeEvidence(name=name, status="skipped", missing_requirements=missing)
    return RealSmokeEvidence(name=name, status="passed", summary="enabled")


def write_pilot_smoke_artifact(path: Path, scenarios: list[PilotSmokeScenario]) -> Path:
    """Write deterministic local Pilot smoke evidence for human review."""
    missing_by_scenario = {
        scenario.name: scenario.missing_keys() for scenario in scenarios if scenario.missing_keys()
    }
    if missing_by_scenario:
        details = "; ".join(
            f"{name}: {', '.join(keys)}" for name, keys in sorted(missing_by_scenario.items())
        )
        raise ValueError(f"Pilot smoke scenario evidence is incomplete: {details}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "passed",
                "scenarios": [scenario.to_json() for scenario in scenarios],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def recommend(
    command_results: list[CommandResult],
    capability_evidence: list[CapabilityEvidence],
    real_smoke: list[RealSmokeEvidence],
    issues: list[VerificationIssue],
) -> Recommendation:
    """Return the final Go / Conditional Go / No-Go recommendation."""
    if any(issue.classification == "Pilot blocker" for issue in issues):
        return "No-Go"
    if any(result.status == "failed" for result in command_results):
        return "No-Go"
    if any(evidence.status == "failed" for evidence in capability_evidence):
        return "No-Go"
    if any(item.status == "failed" for item in real_smoke):
        return "Conditional Go"
    if any(issue.classification in {"Docs gap", "Enhancement"} for issue in issues):
        return "Conditional Go"
    return "Go"


def render_json_report(report: PilotVerificationReport) -> str:
    """Render the verification report as stable JSON."""
    return json.dumps(report.to_json(), ensure_ascii=False, indent=2, sort_keys=True)


def render_markdown_report(report: PilotVerificationReport) -> str:
    """Render the verification report as human-readable Markdown."""
    lines = [
        "# Pilot Capability Verification Report",
        "",
        "## Run Metadata",
        "",
        f"- Git SHA: `{report.metadata.git_sha}`",
        f"- Python: `{report.metadata.python_version}`",
        f"- Generated at: `{report.metadata.generated_at.isoformat()}`",
        f"- Artifact dir: `{report.metadata.artifact_dir}`",
        "",
        "## Automated Checks",
        "",
    ]
    if report.command_results:
        for result in report.command_results:
            lines.append(f"- `{result.command}`: **{result.status}**")
    else:
        lines.append("- No command results were imported.")
    lines.extend(["", "## Capability Evidence", ""])
    for evidence in report.capability_evidence:
        lines.extend(
            [
                f"### {evidence.capability}",
                "",
                f"- Status: **{evidence.status}**",
                f"- Command: `{evidence.command}`",
                "- Artifacts: " + ", ".join(f"`{path}`" for path in evidence.artifacts),
            ]
        )
        for note in evidence.notes:
            lines.append(f"- Evidence: {note}")
        lines.append("")
    lines.extend(["## Real Smoke Evidence", ""])
    if report.real_smoke:
        for smoke in report.real_smoke:
            reason = f" ({smoke.skip_reason})" if smoke.skip_reason else ""
            lines.append(f"- {smoke.name}: **{smoke.status}**{reason}")
    else:
        lines.append("- No real smoke results were imported.")
    lines.extend(["", "## Config Validation", ""])
    if report.config_validation:
        lines.append(f"- Status: **{report.config_validation.status}**")
        lines.append(f"- Errors: {report.config_validation.error_count}")
        lines.append(f"- Skipped: {report.config_validation.skipped_count}")
    else:
        lines.append("- No config validation evidence imported.")
    lines.extend(["", "## Diagnostics Evidence", ""])
    if report.diagnostics:
        lines.append(f"- Manifest: `{report.diagnostics.manifest_path}`")
        lines.append(f"- Artifacts: {report.diagnostics.artifact_count}")
    else:
        lines.append("- No diagnostics manifest imported.")
    lines.extend(["", "## Connector Status", ""])
    if report.connector_status:
        for status in report.connector_status:
            lines.append(f"- `{status.get('connector_id')}`: {status.get('last_status')}")
    else:
        lines.append("- No connector status imported.")
    lines.extend(["", "## Issues", ""])
    if report.issues:
        for issue in report.issues:
            lines.append(f"- **{issue.classification}** `{issue.source}`: {issue.title}")
    else:
        lines.append("- No issues recorded.")
    lines.extend(["", "## Final Recommendation", "", f"**{report.recommendation}**", ""])
    return "\n".join(lines)


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _python_version() -> str:
    return sys.version.split()[0]
