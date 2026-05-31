"""Usage summary public API."""

from dataclasses import dataclass
from datetime import datetime

from fleetent.observability.traces import TraceQuery, query_trace_events


@dataclass(frozen=True)
class UsageQuery:
    """Usage summary query filters."""

    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = 10_000


@dataclass(frozen=True)
class ModelUsage:
    """Usage summary grouped by model."""

    model: str
    run_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_elapsed_s: float
    avg_elapsed_s: float


@dataclass(frozen=True)
class UsageSummary:
    """Aggregated usage summary."""

    run_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_elapsed_s: float
    avg_elapsed_s: float
    by_model: list[ModelUsage]


def get_usage_summary(query: UsageQuery) -> UsageSummary:
    """Return usage aggregates from agent_run_completed trace events."""
    events = query_trace_events(
        TraceQuery(
            user_id=query.user_id,
            agent_id=query.agent_id,
            tenant_id=query.tenant_id,
            event_type="agent_run_completed",
            start_ts=query.start_ts,
            end_ts=query.end_ts,
            limit=query.limit,
        )
    )
    run_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    total_elapsed_s = 0.0
    by_model: dict[str, dict[str, float | int]] = {}

    for event in events:
        if event.event_type != "agent_run_completed":
            continue
        if query.session_id is not None and event.session_id != query.session_id:
            continue
        tokens = event.payload.get("tokens") or {}
        prompt = _to_int(tokens.get("prompt")) if isinstance(tokens, dict) else 0
        completion = _to_int(tokens.get("completion")) if isinstance(tokens, dict) else 0
        total = _to_int(tokens.get("total", prompt + completion)) if isinstance(tokens, dict) else 0
        elapsed_s = _to_float(event.payload.get("elapsed_s"))

        run_count += 1
        prompt_tokens += prompt
        completion_tokens += completion
        total_tokens += total
        total_elapsed_s += elapsed_s
        model = str(event.payload.get("model_used") or "unknown")
        model_totals = by_model.setdefault(
            model,
            {
                "run_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_elapsed_s": 0.0,
            },
        )
        model_totals["run_count"] += 1
        model_totals["prompt_tokens"] += prompt
        model_totals["completion_tokens"] += completion
        model_totals["total_tokens"] += total
        model_totals["total_elapsed_s"] += elapsed_s

    avg_elapsed_s = total_elapsed_s / run_count if run_count else 0
    return UsageSummary(
        run_count=run_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        total_elapsed_s=total_elapsed_s,
        avg_elapsed_s=avg_elapsed_s,
        by_model=_build_model_usage(by_model),
    )


def _build_model_usage(by_model: dict[str, dict[str, float | int]]) -> list[ModelUsage]:
    models: list[ModelUsage] = []
    for model, totals in by_model.items():
        model_run_count = int(totals["run_count"])
        model_elapsed_s = float(totals["total_elapsed_s"])
        models.append(
            ModelUsage(
                model=model,
                run_count=model_run_count,
                prompt_tokens=int(totals["prompt_tokens"]),
                completion_tokens=int(totals["completion_tokens"]),
                total_tokens=int(totals["total_tokens"]),
                total_elapsed_s=model_elapsed_s,
                avg_elapsed_s=model_elapsed_s / model_run_count if model_run_count else 0,
            )
        )
    return sorted(models, key=lambda item: (-item.total_tokens, item.model))


def _to_int(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int | float | str):
        try:
            return int(value)
        except ValueError:
            return 0
    try:
        return int(str(value))
    except ValueError:
        return 0


def _to_float(value: object) -> float:
    if value is None or value == "":
        return 0
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return 0
    try:
        return float(str(value))
    except ValueError:
        return 0
