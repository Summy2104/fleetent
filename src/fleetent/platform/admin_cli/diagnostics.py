"""Diagnostics admin CLI commands."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from fleetent.platform.admin_cli.common import sanitize_cli_value


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register diagnostics commands."""
    p_diagnostics = subparsers.add_parser("diagnostics", help="Diagnostics export and retention")
    diagnostics_sub = p_diagnostics.add_subparsers(dest="diagnostics_cmd", required=True)
    p_diag_export = diagnostics_sub.add_parser(
        "export", help="Export sanitized diagnostics package"
    )
    p_diag_export.add_argument("--from", dest="from_ts", default=None)
    p_diag_export.add_argument("--to", dest="to_ts", default=None)
    p_diag_export.add_argument("--output-dir", default=None)
    p_diag_retention = diagnostics_sub.add_parser("retention", help="Diagnostics retention")
    retention_sub = p_diag_retention.add_subparsers(dest="retention_cmd", required=True)
    retention_sub.add_parser("dry-run", help="Plan diagnostics retention")
    retention_sub.add_parser("apply", help="Apply diagnostics retention")


def handle(args: argparse.Namespace) -> bool:
    """Handle diagnostics commands."""
    if args.cmd != "diagnostics":
        return False

    from fleetent.observability import diagnostics

    if args.diagnostics_cmd == "export":
        request = diagnostics.DiagnosticsExportRequest(
            output_dir=Path(args.output_dir) if args.output_dir else None,
            start_ts=datetime.fromisoformat(args.from_ts) if args.from_ts else None,
            end_ts=datetime.fromisoformat(args.to_ts) if args.to_ts else None,
        )
        package = diagnostics.export_diagnostics(request)
        print(f"package={sanitize_cli_value(package.path)}")
        return True

    if args.diagnostics_cmd == "retention" and args.retention_cmd == "dry-run":
        plan = diagnostics.plan_diagnostics_retention()
        print(
            " ".join(
                [
                    f"logs={len(plan.log_files)}",
                    f"traces={plan.trace_count}",
                    f"exports={len(plan.diagnostic_exports)}",
                ]
            )
        )
        return True

    if args.diagnostics_cmd == "retention" and args.retention_cmd == "apply":
        result = diagnostics.apply_diagnostics_retention()
        if not result.applied:
            print(sanitize_cli_value(result.message), file=sys.stderr)
            sys.exit(1)
        print(
            " ".join(
                [
                    f"deleted_logs={result.deleted_logs}",
                    f"deleted_traces={result.deleted_traces}",
                    f"deleted_exports={result.deleted_exports}",
                    f"failures={len(result.failures)}",
                ]
            )
        )
        return True

    return True
