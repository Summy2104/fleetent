from __future__ import annotations

import argparse
import json
import sys

from fleetent.platform import maintenance as maintenance_service
from fleetent.platform.maintenance import MaintenanceSummary
from fleetent.platform.platform_cli.common import sanitize_cli_value, summary_line


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("maintenance", help="Manual maintenance entrypoints")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--actor", default="operator")
    sub = parser.add_subparsers(dest="maintenance_domain", required=True)

    memory = sub.add_parser("memory", help="Memory maintenance")
    memory_sub = memory.add_subparsers(dest="maintenance_action", required=True)
    compact = memory_sub.add_parser("compact")
    compact_sub = compact.add_subparsers(dest="maintenance_mode", required=True)
    compact_sub.add_parser("dry-run")
    _add_common_apply_args(compact_sub.add_parser("apply"))

    reflection = sub.add_parser("reflection", help="Reflection maintenance")
    reflection_sub = reflection.add_subparsers(dest="maintenance_action", required=True)
    run = reflection_sub.add_parser("run")
    run.add_argument("--scope", required=True)
    run.add_argument("--dry-run", action="store_true")
    _add_common_apply_args(run)


def handle(args: argparse.Namespace) -> bool:
    if args.cmd != "maintenance":
        return False

    try:
        if getattr(args, "actor", None) is None:
            args.actor = "operator"
        summary = _run(args)
    except maintenance_service.ConfirmationRequired as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    _print_summary(summary, json_format=args.format == "json")
    return True


def _run(args: argparse.Namespace) -> MaintenanceSummary:
    if args.maintenance_domain == "memory" and args.maintenance_action == "compact":
        dry_run = args.maintenance_mode == "dry-run"
        if not dry_run:
            maintenance_service.require_confirmation(
                yes=args.yes,
                dry_run_command="fleetent platform maintenance memory compact dry-run",
            )
        return maintenance_service.compact_memory(dry_run=dry_run, actor=args.actor)

    if args.maintenance_domain == "reflection" and args.maintenance_action == "run":
        if not args.dry_run:
            maintenance_service.require_confirmation(
                yes=args.yes,
                dry_run_command=(
                    f"fleetent platform maintenance reflection run --dry-run --scope {args.scope}"
                ),
            )
        return maintenance_service.run_reflection(
            scope=args.scope, dry_run=args.dry_run, actor=args.actor
        )

    raise maintenance_service.ConfirmationRequired("unsupported maintenance command")


def _print_summary(summary: MaintenanceSummary, *, json_format: bool) -> None:
    if json_format:
        print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    print(f"command={sanitize_cli_value(summary.command)}")
    print(f"dry_run={summary.dry_run}")
    if summary.affected_counts:
        print(summary_line(summary.affected_counts))
    if summary.skipped_reasons:
        print("skipped=" + sanitize_cli_value(", ".join(summary.skipped_reasons)))
    if summary.audit_ref:
        print(f"audit_ref={sanitize_cli_value(summary.audit_ref)}")


def _add_yes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true")


def _add_common_apply_args(parser: argparse.ArgumentParser) -> None:
    _add_yes(parser)
    parser.add_argument("--actor", default=None)
