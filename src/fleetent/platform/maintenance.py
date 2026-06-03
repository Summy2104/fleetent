from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fleetent.observability.traces import TraceEvent, record_trace_event


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
    command = "memory compact"
    return MaintenanceSummary(
        command=command,
        dry_run=dry_run,
        affected_counts={"memories_compacted": 0},
        audit_ref=None if dry_run else _record_maintenance_trace(command, actor),
    )


def run_kb_sync(*, connector_id: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    command = "kb sync"
    return MaintenanceSummary(
        command=command,
        dry_run=dry_run,
        affected_counts={"connectors": 1 if connector_id else 0},
        audit_ref=None
        if dry_run
        else _record_maintenance_trace(command, actor, {"connector_id": connector_id}),
    )


def reindex_vector(*, namespace: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    command = "vector reindex"
    return MaintenanceSummary(
        command=command,
        dry_run=dry_run,
        affected_counts={"namespaces": 1 if namespace else 0},
        audit_ref=None
        if dry_run
        else _record_maintenance_trace(command, actor, {"namespace": namespace}),
    )


def run_reflection(*, scope: str, dry_run: bool, actor: str) -> MaintenanceSummary:
    command = "reflection run"
    return MaintenanceSummary(
        command=command,
        dry_run=dry_run,
        affected_counts={"scopes": 1 if scope else 0},
        audit_ref=None if dry_run else _record_maintenance_trace(command, actor, {"scope": scope}),
    )


def _record_maintenance_trace(
    command: str,
    actor: str,
    extra_payload: dict[str, object] | None = None,
) -> str:
    trace_id = str(uuid.uuid4())
    payload = {"actor": actor, "command": command, **(extra_payload or {})}
    record_trace_event(
        TraceEvent(
            id=trace_id,
            run_id=f"maintenance:{trace_id}",
            event_type="maintenance_operation",
            payload=payload,
        )
    )
    return f"trace:{trace_id}"
