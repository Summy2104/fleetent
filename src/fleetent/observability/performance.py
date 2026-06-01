"""Performance summary public API."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from fleetent.observability.traces import TraceQuery, query_trace_events

_RUN_COMPLETED = "agent_run_completed"
_RUN_FAILED = "agent_run_failed"
_LLM_COMPLETED = "llm_call_completed"
_LLM_FAILED = "llm_call_failed"
_FALLBACK_TRIGGERED = "model_fallback_triggered"
_TOOL_COMPLETED = "tool_call_completed"
_TOOL_FAILED = "tool_call_failed"
_PERMISSION_REQUESTED = "permission_requested"
_PERMISSION_RESOLVED = "permission_resolved"


@dataclass(frozen=True)
class PerformanceQuery:
    """Performance summary query filters."""

    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = 10_000


@dataclass(frozen=True)
class ModelPerformance:
    """Performance summary grouped by model."""

    model: str
    call_count: int
    error_count: int
    avg_elapsed_s: float


@dataclass(frozen=True)
class ToolPerformance:
    """Performance summary grouped by tool."""

    tool_name: str
    call_count: int
    error_count: int
    avg_elapsed_s: float


@dataclass(frozen=True)
class PermissionSummary:
    """Permission wait performance summary."""

    requested_count: int
    approved_count: int
    rejected_count: int
    timeout_count: int
    avg_wait_s: float


@dataclass(frozen=True)
class PerformanceSummary:
    """Aggregated performance summary."""

    run_count: int
    completed_count: int
    failed_count: int
    failure_rate: float
    avg_elapsed_s: float
    p50_elapsed_s: float
    p95_elapsed_s: float
    llm_call_count: int
    llm_error_count: int
    avg_llm_elapsed_s: float
    p95_llm_elapsed_s: float
    fallback_count: int
    fallback_rate: float
    tool_call_count: int
    tool_error_count: int
    avg_tool_elapsed_s: float
    p95_tool_elapsed_s: float
    permission_requested_count: int
    permission_approved_count: int
    permission_rejected_count: int
    permission_timeout_count: int
    avg_permission_wait_s: float
    by_model: list[ModelPerformance]
    by_tool: list[ToolPerformance]
    permission: PermissionSummary


def get_performance_summary(query: PerformanceQuery) -> PerformanceSummary:
    """Return performance aggregates from trace events."""
    events = query_trace_events(
        TraceQuery(
            user_id=query.user_id,
            agent_id=query.agent_id,
            tenant_id=query.tenant_id,
            start_ts=query.start_ts,
            end_ts=query.end_ts,
            limit=query.limit,
        )
    )
    completed_count = 0
    failed_count = 0
    fallback_count = 0
    run_elapsed_samples: list[float] = []
    llm_call_count = 0
    llm_error_count = 0
    llm_elapsed_samples: list[float] = []
    by_model: dict[str, _GroupTotals] = {}
    tool_call_count = 0
    tool_error_count = 0
    tool_elapsed_samples: list[float] = []
    by_tool: dict[str, _GroupTotals] = {}
    permission_requested_count = 0
    permission_approved_count = 0
    permission_rejected_count = 0
    permission_timeout_count = 0
    permission_wait_samples: list[float] = []

    for event in events:
        if query.session_id is not None and event.session_id != query.session_id:
            continue
        if event.event_type == _RUN_COMPLETED:
            completed_count += 1
            _append_elapsed_sample(run_elapsed_samples, event.payload.get("elapsed_s"))
        elif event.event_type == _RUN_FAILED:
            failed_count += 1
            _append_elapsed_sample(run_elapsed_samples, event.payload.get("elapsed_s"))
        elif event.event_type in {_LLM_COMPLETED, _LLM_FAILED}:
            llm_call_count += 1
            is_error = event.event_type == _LLM_FAILED
            if is_error:
                llm_error_count += 1
            elapsed = _to_float(event.payload.get("elapsed_s"))
            if elapsed is not None:
                llm_elapsed_samples.append(elapsed)
            model = _group_key(event.payload.get("model"))
            _record_group(by_model, model, is_error=is_error, elapsed_s=elapsed)
        elif event.event_type == _FALLBACK_TRIGGERED:
            fallback_count += 1
        elif event.event_type in {_TOOL_COMPLETED, _TOOL_FAILED}:
            tool_call_count += 1
            is_error = event.event_type == _TOOL_FAILED
            if is_error:
                tool_error_count += 1
            elapsed = _to_float(event.payload.get("elapsed_s"))
            if elapsed is not None:
                tool_elapsed_samples.append(elapsed)
            tool_name = _group_key(event.payload.get("tool_name"))
            _record_group(by_tool, tool_name, is_error=is_error, elapsed_s=elapsed)
        elif event.event_type == _PERMISSION_REQUESTED:
            permission_requested_count += 1
        elif event.event_type == _PERMISSION_RESOLVED:
            decision = _group_key(event.payload.get("decision")).lower()
            if decision == "approved":
                permission_approved_count += 1
            elif decision == "rejected":
                permission_rejected_count += 1
            elif decision == "timeout":
                permission_timeout_count += 1
            _append_elapsed_sample(permission_wait_samples, event.payload.get("elapsed_s"))

    run_count = completed_count + failed_count

    permission = PermissionSummary(
        requested_count=permission_requested_count,
        approved_count=permission_approved_count,
        rejected_count=permission_rejected_count,
        timeout_count=permission_timeout_count,
        avg_wait_s=_average(permission_wait_samples),
    )
    return PerformanceSummary(
        run_count=run_count,
        completed_count=completed_count,
        failed_count=failed_count,
        failure_rate=failed_count / run_count if run_count else 0,
        avg_elapsed_s=_average(run_elapsed_samples),
        p50_elapsed_s=_percentile(run_elapsed_samples, 50),
        p95_elapsed_s=_percentile(run_elapsed_samples, 95),
        llm_call_count=llm_call_count,
        llm_error_count=llm_error_count,
        avg_llm_elapsed_s=_average(llm_elapsed_samples),
        p95_llm_elapsed_s=_percentile(llm_elapsed_samples, 95),
        fallback_count=fallback_count,
        fallback_rate=fallback_count / run_count if run_count else 0,
        tool_call_count=tool_call_count,
        tool_error_count=tool_error_count,
        avg_tool_elapsed_s=_average(tool_elapsed_samples),
        p95_tool_elapsed_s=_percentile(tool_elapsed_samples, 95),
        permission_requested_count=permission_requested_count,
        permission_approved_count=permission_approved_count,
        permission_rejected_count=permission_rejected_count,
        permission_timeout_count=permission_timeout_count,
        avg_permission_wait_s=permission.avg_wait_s,
        by_model=_build_model_performance(by_model),
        by_tool=_build_tool_performance(by_tool),
        permission=permission,
    )


@dataclass
class _GroupTotals:
    call_count: int = 0
    error_count: int = 0
    elapsed_samples: list[float] | None = None

    def record(self, *, is_error: bool, elapsed_s: float | None) -> None:
        self.call_count += 1
        if is_error:
            self.error_count += 1
        if elapsed_s is None:
            return
        if self.elapsed_samples is None:
            self.elapsed_samples = []
        self.elapsed_samples.append(elapsed_s)


def _record_group(
    groups: dict[str, _GroupTotals],
    key: str,
    *,
    is_error: bool,
    elapsed_s: float | None,
) -> None:
    groups.setdefault(key, _GroupTotals()).record(is_error=is_error, elapsed_s=elapsed_s)


def _build_model_performance(by_model: dict[str, _GroupTotals]) -> list[ModelPerformance]:
    models = [
        ModelPerformance(
            model=model,
            call_count=totals.call_count,
            error_count=totals.error_count,
            avg_elapsed_s=_average(totals.elapsed_samples or []),
        )
        for model, totals in by_model.items()
    ]
    return sorted(models, key=lambda item: (-item.call_count, item.model))


def _build_tool_performance(by_tool: dict[str, _GroupTotals]) -> list[ToolPerformance]:
    tools = [
        ToolPerformance(
            tool_name=tool_name,
            call_count=totals.call_count,
            error_count=totals.error_count,
            avg_elapsed_s=_average(totals.elapsed_samples or []),
        )
        for tool_name, totals in by_tool.items()
    ]
    return sorted(tools, key=lambda item: (-item.call_count, item.tool_name))


def _group_key(value: object) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value)


def _append_elapsed_sample(samples: list[float], value: object) -> None:
    elapsed = _to_float(value)
    if elapsed is not None:
        samples.append(elapsed)


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    parsed: float
    if isinstance(value, int | float | str):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
    else:
        try:
            parsed = float(str(value))
        except (TypeError, ValueError):
            return None
    return parsed if isfinite(parsed) else None


def _average(samples: list[float]) -> float:
    return sum(samples) / len(samples) if samples else 0


def _percentile(samples: list[float], percentile: int) -> float:
    if not samples:
        return 0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, (percentile * len(ordered) + 99) // 100 - 1))
    return ordered[index]
