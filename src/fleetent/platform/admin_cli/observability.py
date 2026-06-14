"""Observability admin CLI commands."""

from __future__ import annotations

import argparse

from fleetent.platform.admin_cli.common import (
    format_optional,
    parse_iso_time,
    payload_keys,
    sanitize_cli_value,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register observability commands."""
    p_observability = subparsers.add_parser("observability", help="Observability queries")
    observability_sub = p_observability.add_subparsers(dest="observability_cmd", required=True)
    p_obs_traces = observability_sub.add_parser("traces", help="Query agent run traces")
    _add_filters(p_obs_traces)
    p_obs_traces.add_argument("--run-id", default=None)
    p_obs_traces.add_argument("--event-type", default=None)
    p_obs_usage = observability_sub.add_parser("usage", help="Query usage summary")
    _add_filters(p_obs_usage)
    p_obs_performance = observability_sub.add_parser(
        "performance", help="Query performance summary"
    )
    _add_filters(p_obs_performance)


def handle(args: argparse.Namespace) -> bool:
    """Handle observability commands."""
    if args.cmd != "observability":
        return False

    from fleetent import observability

    if args.observability_cmd == "traces":
        events = observability.query_trace_events(
            observability.TraceQuery(
                run_id=args.run_id,
                user_id=args.user_id,
                agent_name=args.agent_id,
                session_id=args.session_id,
                tenant_id=args.tenant_id,
                event_type=args.event_type,
                start_ts=parse_iso_time(args.from_ts, "--from"),
                end_ts=parse_iso_time(args.to_ts, "--to"),
                limit=args.limit,
            )
        )
        print(
            f"{'TS':<25}  {'RUN_ID':<18}  {'EVENT_TYPE':<28}  "
            f"{'USER_ID':<16}  {'AGENT_NAME':<16}  {'SESSION_ID':<16}  PAYLOAD_KEYS"
        )
        for event in events:
            print(
                f"{format_optional(event.ts.isoformat() if event.ts else None):<25}  "
                f"{event.run_id:<18}  {event.event_type:<28}  "
                f"{format_optional(event.user_id):<16}  {format_optional(event.agent_name):<16}  "
                f"{format_optional(event.session_id):<16}  {payload_keys(event.payload)}"
            )
        return True

    if args.observability_cmd == "usage":
        usage_summary = observability.get_usage_summary(
            observability.UsageQuery(
                user_id=args.user_id,
                agent_name=args.agent_id,
                tenant_id=args.tenant_id,
                session_id=args.session_id,
                start_ts=parse_iso_time(args.from_ts, "--from"),
                end_ts=parse_iso_time(args.to_ts, "--to"),
                limit=args.limit,
            )
        )
        print(
            " ".join(
                [
                    f"run_count={usage_summary.run_count}",
                    f"prompt_tokens={usage_summary.prompt_tokens}",
                    f"completion_tokens={usage_summary.completion_tokens}",
                    f"total_tokens={usage_summary.total_tokens}",
                    f"avg_elapsed_s={usage_summary.avg_elapsed_s:.3f}",
                ]
            )
        )
        for model_usage in usage_summary.by_model:
            print(
                " ".join(
                    [
                        f"model={sanitize_cli_value(model_usage.model)}",
                        f"run_count={model_usage.run_count}",
                        f"total_tokens={model_usage.total_tokens}",
                        f"avg_elapsed_s={model_usage.avg_elapsed_s:.3f}",
                    ]
                )
            )
        return True

    if args.observability_cmd == "performance":
        performance_summary = observability.get_performance_summary(
            observability.PerformanceQuery(
                user_id=args.user_id,
                agent_name=args.agent_id,
                tenant_id=args.tenant_id,
                session_id=args.session_id,
                start_ts=parse_iso_time(args.from_ts, "--from"),
                end_ts=parse_iso_time(args.to_ts, "--to"),
                limit=args.limit,
            )
        )
        print(
            " ".join(
                [
                    f"run_count={performance_summary.run_count}",
                    f"completed={performance_summary.completed_count}",
                    f"failed={performance_summary.failed_count}",
                    f"failure_rate={performance_summary.failure_rate:.3f}",
                    f"avg_elapsed_s={performance_summary.avg_elapsed_s:.3f}",
                    f"p50_elapsed_s={performance_summary.p50_elapsed_s:.3f}",
                    f"p95_elapsed_s={performance_summary.p95_elapsed_s:.3f}",
                ]
            )
        )
        print(
            " ".join(
                [
                    f"llm_calls={performance_summary.llm_call_count}",
                    f"llm_errors={performance_summary.llm_error_count}",
                    f"avg_llm_elapsed_s={performance_summary.avg_llm_elapsed_s:.3f}",
                    f"p95_llm_elapsed_s={performance_summary.p95_llm_elapsed_s:.3f}",
                    f"fallbacks={performance_summary.fallback_count}",
                    f"fallback_rate={performance_summary.fallback_rate:.3f}",
                ]
            )
        )
        print(
            " ".join(
                [
                    f"tool_calls={performance_summary.tool_call_count}",
                    f"tool_errors={performance_summary.tool_error_count}",
                    f"avg_tool_elapsed_s={performance_summary.avg_tool_elapsed_s:.3f}",
                    f"p95_tool_elapsed_s={performance_summary.p95_tool_elapsed_s:.3f}",
                ]
            )
        )
        print(
            " ".join(
                [
                    f"permission_requested={performance_summary.permission_requested_count}",
                    f"permission_approved={performance_summary.permission_approved_count}",
                    f"permission_rejected={performance_summary.permission_rejected_count}",
                    f"permission_timeout={performance_summary.permission_timeout_count}",
                    f"avg_permission_wait_s={performance_summary.avg_permission_wait_s:.3f}",
                ]
            )
        )
        for model_performance in performance_summary.by_model:
            print(
                " ".join(
                    [
                        f"model={sanitize_cli_value(model_performance.model)}",
                        f"calls={model_performance.call_count}",
                        f"errors={model_performance.error_count}",
                        f"avg_elapsed_s={model_performance.avg_elapsed_s:.3f}",
                    ]
                )
            )
        for tool_performance in performance_summary.by_tool:
            print(
                " ".join(
                    [
                        f"tool={sanitize_cli_value(tool_performance.tool_name)}",
                        f"calls={tool_performance.call_count}",
                        f"errors={tool_performance.error_count}",
                        f"avg_elapsed_s={tool_performance.avg_elapsed_s:.3f}",
                    ]
                )
            )
        return True

    return True


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--from", dest="from_ts", default=None)
    parser.add_argument("--to", dest="to_ts", default=None)
    parser.add_argument("--limit", type=int, default=100)
