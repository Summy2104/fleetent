"""IM connector registry + channel allowlist admin CLI commands.

Distinct from `im.py` (IM *user* approval). These manage the connector registry
(credentials, enable/disable) and the per-platform channel allowlist.
"""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register IM connector + channel allowlist commands."""
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

    p_chan = subparsers.add_parser("im-channel", help="IM channel allowlist administration")
    chan_sub = p_chan.add_subparsers(dest="im_channel_cmd", required=True)
    p_allow = chan_sub.add_parser("allow", help="Add a channel/workspace allowlist entry")
    p_allow.add_argument("--platform", required=True)
    p_allow.add_argument("--scope-type", required=True, choices=["channel", "workspace"])
    p_allow.add_argument("--scope-id", required=True)
    p_allow.add_argument("--note")
    p_dis = chan_sub.add_parser("disallow", help="Remove an allowlist entry by id")
    p_dis.add_argument("--id", required=True, type=int)
    p_list = chan_sub.add_parser("list", help="List allowlist entries")
    p_list.add_argument("--platform")


def handle(args: argparse.Namespace) -> bool:
    """Handle IM connector + channel allowlist commands."""
    if args.cmd == "im-connector":
        _handle_connector(args)
        return True
    if args.cmd == "seed-connectors":
        from fleetent.platform import im_gateway_management as im

        seeded = im.seed_from_env()
        print("Seeded: " + (", ".join(seeded) if seeded else "(none)"))
        return True
    if args.cmd == "im-channel":
        _handle_channel(args)
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


def _handle_channel(args: argparse.Namespace) -> None:
    from fleetent import user_store
    from fleetent.platform import im_gateway_management as im

    owner = user_store.admin_owner_id()

    if args.im_channel_cmd == "allow":
        try:
            im.add_entry(owner, args.platform, args.scope_type, args.scope_id, args.note)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(2) from exc
        print(f"allowed {args.platform} {args.scope_type}:{args.scope_id}")
        return

    if args.im_channel_cmd == "disallow":
        im.remove_entry(args.id)
        print(f"removed allowlist entry {args.id}")
        return

    if args.im_channel_cmd == "list":
        entries = im.list_entries(None, args.platform)
        if not entries:
            print("No allowlist entries.")
            return
        print(f"{'ID':<6}  {'PLATFORM':<12}  {'SCOPE_TYPE':<10}  {'SCOPE_ID':<24}  NOTE")
        for row in entries:
            print(
                f"{row['id']:<6}  {row['platform']:<12}  {row['scope_type']:<10}  "
                f"{row['scope_id']:<24}  {row.get('note') or ''}"
            )
        return
