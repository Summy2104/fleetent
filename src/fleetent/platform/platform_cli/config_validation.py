from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("validate-config", help="Validate runtime configuration")
    parser.add_argument("--profile", choices=["dev", "pilot", "production"], default="dev")
    parser.add_argument("--format", choices=["text", "json"], default="text")


def handle(args: argparse.Namespace) -> bool:
    if args.cmd != "validate-config":
        return False
    from fleetent.platform.config_validation import render_text, validate_config

    report = validate_config(profile=args.profile)
    print(report.to_json() if args.format == "json" else render_text(report))
    if report.final_status == "error":
        sys.exit(1)
    return True
