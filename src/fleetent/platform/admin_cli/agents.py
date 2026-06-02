"""Agent and channel admin CLI commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_SETTINGS_YAML = Path("config/settings.yaml")


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register agent and channel commands."""
    p_assign_ch = subparsers.add_parser("assign-channel", help="Bind an agent to a channel")
    p_assign_ch.add_argument("--platform", required=True)
    p_assign_ch.add_argument("--channel-id", required=True)
    p_assign_ch.add_argument("--agent-name", required=True)

    p_unassign_ch = subparsers.add_parser("unassign-channel", help="Remove channel-agent binding")
    p_unassign_ch.add_argument("--platform", required=True)
    p_unassign_ch.add_argument("--channel-id", required=True)

    p_default = subparsers.add_parser("set-default-agent", help="Set or clear the default agent")
    p_default_group = p_default.add_mutually_exclusive_group(required=True)
    p_default_group.add_argument("--agent-name", help="Agent name to set as default")
    p_default_group.add_argument("--clear", action="store_true", help="Clear default agent")


def handle(args: argparse.Namespace) -> bool:
    """Handle agent and channel commands."""
    if args.cmd == "assign-channel":
        from fleetent.agent_store import assign_channel, get_by_name

        agent = get_by_name(args.agent_name)
        if agent is None:
            print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
            sys.exit(1)
        assign_channel(args.platform, args.channel_id, agent.id)
        print(f"Channel {args.platform}/{args.channel_id} → agent '{args.agent_name}'.")
        return True

    if args.cmd == "unassign-channel":
        from fleetent.agent_store import unassign_channel

        unassign_channel(args.platform, args.channel_id)
        print(f"Channel {args.platform}/{args.channel_id} unassigned.")
        return True

    if args.cmd == "set-default-agent":
        _set_default_agent(args)
        return True

    return False


def _set_default_agent(args: argparse.Namespace) -> None:
    data: dict[str, object] = {}
    if _SETTINGS_YAML.exists():
        data = yaml.safe_load(_SETTINGS_YAML.read_text()) or {}

    if args.clear:
        data.pop("default_agent_name", None)
        print("Default agent cleared.")
    else:
        data["default_agent_name"] = args.agent_name
        print(f"Default agent set to '{args.agent_name}'.")

    _SETTINGS_YAML.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_YAML.write_text(yaml.safe_dump(data))
