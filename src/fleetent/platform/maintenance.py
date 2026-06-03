from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaintenanceSummary:
    command: str
    dry_run: bool
    affected_counts: dict[str, int] = field(default_factory=dict)
    skipped_reasons: list[str] = field(default_factory=list)
    audit_ref: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "affected_counts": dict(sorted(self.affected_counts.items())),
            "audit_ref": self.audit_ref,
            "command": self.command,
            "dry_run": self.dry_run,
            "skipped_reasons": list(self.skipped_reasons),
        }


def require_confirmation(*, yes: bool, dry_run_command: str) -> None:
    if not yes:
        raise ConfirmationRequired(
            "destructive maintenance operation requires --yes; "
            f"run dry-run first: {dry_run_command}"
        )


class ConfirmationRequiredError(RuntimeError):
    pass


ConfirmationRequired = ConfirmationRequiredError


def compact_memory(*, dry_run: bool, actor: str) -> MaintenanceSummary:
    return MaintenanceSummary(
        command="memory compact",
        dry_run=dry_run,
        affected_counts={"memories_compacted": 0},
        audit_ref=None if dry_run else f"audit:memory:compact:{actor}",
    )


def run_kb_sync(*, connector_id: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    return MaintenanceSummary(
        command="kb sync",
        dry_run=dry_run,
        affected_counts={"connectors": 1 if connector_id else 0},
        audit_ref=None if dry_run else f"audit:kb:sync:{actor}:{connector_id}",
    )


def reindex_vector(*, namespace: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    return MaintenanceSummary(
        command="vector reindex",
        dry_run=dry_run,
        affected_counts={"namespaces": 1 if namespace else 0},
        audit_ref=None if dry_run else f"audit:vector:reindex:{actor}:{namespace}",
    )


def run_reflection(*, scope: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    return MaintenanceSummary(
        command="reflection run",
        dry_run=dry_run,
        affected_counts={"scopes": 1 if scope else 0},
        audit_ref=None if dry_run else f"audit:reflection:run:{actor}:{scope}",
    )
