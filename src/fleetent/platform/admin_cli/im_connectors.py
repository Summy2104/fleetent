"""IM connector registry admin CLI commands."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register IM connector commands."""
    p_conn = subparsers.add_parser("im-connector", help="IM connector registry administration")
    conn_sub = p_conn.add_subparsers(dest="im_connector_cmd", required=True)
    conn_sub.add_parser("list", help="List connectors with masked config")
    for name in ("enable", "disable"):
        p = conn_sub.add_parser(name, help=f"{name.capitalize()} a connector")
        p.add_argument("--platform", required=True)
    p_set = conn_sub.add_parser("set-config", help="Set connector config keys")
    p_set.add_argument("--platform", required=True)
    p_set.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="config key=value"
    )

    subparsers.add_parser("seed-connectors", help="Seed connector configs from .env")


def handle(args: argparse.Namespace) -> bool:
    """Handle IM connector commands."""
    if args.cmd == "im-connector":
        _handle_connector(args)
        return True
    if args.cmd == "seed-connectors":
        from fleetent.platform import im_gateway_management as im

        seeded = im.seed_from_env()
        print("Seeded: " + (", ".join(seeded) if seeded else "(none)"))
        return True
    return False


def _handle_connector(args: argparse.Namespace) -> None:
    from fleetent import user_store
    from fleetent.platform import im_gateway_management as im

    owner = user_store.admin_owner_id()

    if args.im_connector_cmd == "list":
        connectors = im.list_connectors()
        if not connectors:
            print("No connectors configured.")
            return
        print(f"{'OWNER':<14}  {'PLATFORM':<12}  {'ENABLED':<7}  {'STATUS':<14}  CONFIG")
        for row in connectors:
            masked = im.resolve_masked(row["owner_id"], row["platform"])
            config_str = ", ".join(f"{k}={v}" for k, v in masked.items()) or "(none)"
            print(
                f"{row['owner_id']:<14}  {row['platform']:<12}  {str(bool(row['enabled'])):<7}  "
                f"{row['status']:<14}  {config_str}"
            )
        return

    if args.im_connector_cmd in ("enable", "disable"):
        im.set_enabled(owner, args.platform, args.im_connector_cmd == "enable")
        print(f"{args.platform} {args.im_connector_cmd}d")
        return

    if args.im_connector_cmd == "set-config":
        config: dict[str, str] = {}
        for pair in args.set:
            if "=" not in pair:
                print(f"invalid --set value (expected KEY=VALUE): {pair}", file=sys.stderr)
                raise SystemExit(2)
            key, value = pair.split("=", 1)
            config[key] = value
        im.set_config(owner, args.platform, config)
        print(f"{args.platform} config updated ({len(config)} key(s))")
        return
