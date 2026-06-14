"""Agent admin CLI commands."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register agent commands."""
    p_default = subparsers.add_parser("set-default-agent", help="Set or clear the default agent")
    p_default_group = p_default.add_mutually_exclusive_group(required=True)
    p_default_group.add_argument("--agent-name", help="Agent name to set as default")
    p_default_group.add_argument("--clear", action="store_true", help="Clear default agent")

    p_update = subparsers.add_parser("update-agent", help="Create a new agent version")
    p_update.add_argument("--agent-name", required=True)
    p_update.add_argument("--system-prompt")
    p_update.add_argument("--allowed-tools", help="Comma-separated tool patterns")
    p_update.add_argument("--skills-dir")
    p_update.add_argument("--mcp-server-ids", help="Comma-separated MCP server ids")
    p_update.add_argument("--memory-namespace")
    p_update.add_argument(
        "--no-activate", action="store_true", help="Create the version without activating it"
    )

    p_list_v = subparsers.add_parser("list-agent-versions", help="List an agent's versions")
    p_list_v.add_argument("--agent-name", required=True)

    p_activate_v = subparsers.add_parser(
        "activate-agent-version", help="Activate a specific agent version"
    )
    p_activate_v.add_argument("--agent-name", required=True)
    p_activate_v.add_argument("--version", type=int, required=True)

    p_show = subparsers.add_parser("show-agent", help="Show an agent's active version")
    p_show.add_argument("--agent-name", required=True)

    p_assign_u = subparsers.add_parser("assign-user", help="Bind an agent to a user")
    p_assign_u.add_argument("--user-id", required=True)
    p_assign_u.add_argument("--agent-name", required=True)

    p_unassign_u = subparsers.add_parser("unassign-user", help="Remove a user-agent binding")
    p_unassign_u.add_argument("--user-id", required=True)
    p_unassign_u.add_argument("--agent-name", required=True)


def handle(args: argparse.Namespace) -> bool:
    """Handle agent commands."""
    if args.cmd == "set-default-agent":
        _set_default_agent(args)
        return True

    if args.cmd == "update-agent":
        _update_agent(args)
        return True

    if args.cmd == "list-agent-versions":
        _list_agent_versions(args)
        return True

    if args.cmd == "activate-agent-version":
        _activate_agent_version(args)
        return True

    if args.cmd == "show-agent":
        _show_agent(args)
        return True

    if args.cmd == "assign-user":
        _assign_user(args)
        return True

    if args.cmd == "unassign-user":
        _unassign_user(args)
        return True

    return False


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _update_agent(args: argparse.Namespace) -> None:
    from fleetent.agent_store import _UNSET, create_version

    partial: dict[str, object] = {}
    if args.system_prompt is not None:
        partial["system_prompt"] = args.system_prompt
    if args.allowed_tools is not None:
        partial["allowed_tools"] = _csv(args.allowed_tools)
    if args.skills_dir is not None:
        partial["skills_dir"] = args.skills_dir
    if args.mcp_server_ids is not None:
        partial["mcp_server_ids"] = _csv(args.mcp_server_ids)
    if args.memory_namespace is not None:
        partial["memory_namespace"] = args.memory_namespace

    try:
        version = create_version(
            args.agent_name,
            system_prompt=partial.get("system_prompt", _UNSET),
            allowed_tools=partial.get("allowed_tools", _UNSET),
            skills_dir=partial.get("skills_dir", _UNSET),
            mcp_server_ids=partial.get("mcp_server_ids", _UNSET),
            memory_namespace=partial.get("memory_namespace", _UNSET),
            activate=not args.no_activate,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    state = "active" if version.is_active else "inactive"
    print(f"Agent '{args.agent_name}' version {version.version} created ({state}).")


def _list_agent_versions(args: argparse.Namespace) -> None:
    from fleetent.agent_store import list_versions

    versions = list_versions(args.agent_name)
    if not versions:
        print(f"Error: Agent {args.agent_name!r} not found or has no versions.", file=sys.stderr)
        sys.exit(1)
    for v in versions:
        marker = "active" if v.is_active else "      "
        print(f"[{marker}] id={v.id} version={v.version} created_at={v.created_at}")


def _activate_agent_version(args: argparse.Namespace) -> None:
    from fleetent.agent_store import activate_version

    try:
        activate_version(args.agent_name, args.version)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Agent '{args.agent_name}' active version → {args.version}.")


def _show_agent(args: argparse.Namespace) -> None:
    # Authoring/console view → DB active version (not the file-based runtime path).
    from fleetent.runtime.snapshot import load_active_db

    snapshot = load_active_db(args.agent_name)
    if snapshot is None:
        print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
        sys.exit(1)
    print(f"name: {snapshot.name}")
    print(f"version: {snapshot.version}")
    print(f"system_prompt: {snapshot.system_prompt}")
    print(f"allowed_tools: {snapshot.allowed_tools}")
    print(f"skills_dir: {snapshot.skills_dir}")
    print(f"mcp_server_ids: {snapshot.mcp_server_ids}")
    print(f"model_policy: {snapshot.model_policy.model_dump(mode='json')}")
    print(f"memory_namespace: {snapshot.memory_namespace}")


def _assign_user(args: argparse.Namespace) -> None:
    from fleetent.agent_store import assign_user, get_by_name

    agent = get_by_name(args.agent_name)
    if agent is None:
        print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
        sys.exit(1)
    assign_user(args.user_id, agent.id)
    print(f"User {args.user_id} → agent '{args.agent_name}'.")


def _unassign_user(args: argparse.Namespace) -> None:
    from fleetent.agent_store import get_by_name, unassign_user

    agent = get_by_name(args.agent_name)
    if agent is None:
        print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
        sys.exit(1)
    unassign_user(args.user_id, agent.id)
    print(f"User {args.user_id} unassigned from agent '{args.agent_name}'.")


def _agent_yaml_files() -> dict[str, Path]:
    """Map agent name -> its ``agent.yaml`` path in the multi-agent layout."""
    from fleetent import agent_config

    root = agent_config._resolve_agents_dir(None)
    if not root.is_dir():
        return {}
    return {
        p.name: p / agent_config.AGENT_FILE_NAME
        for p in sorted(root.iterdir())
        if (p / agent_config.AGENT_FILE_NAME).is_file()
    }


def _set_agent_default(path: Path, want_default: bool) -> bool:
    """Set/clear ``bindings.default`` in one agent.yaml; return whether it changed."""
    data = yaml.safe_load(path.read_text()) or {}
    bindings = data.get("bindings") or {}
    if bool(bindings.get("default", False)) == want_default:
        return False
    if want_default:
        bindings["default"] = True
    else:
        bindings.pop("default", None)
    data["bindings"] = bindings
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return True


def _set_default_agent(args: argparse.Namespace) -> None:
    # default-agent resolution is the file index's bindings.default winner (zero-DB);
    # this command edits the agent.yaml files, never settings.yaml.
    files = _agent_yaml_files()

    if args.clear:
        cleared = [name for name, path in files.items() if _set_agent_default(path, False)]
        print(f"Default agent cleared from '{cleared[0]}'." if cleared else "No default agent set.")
        return

    if args.agent_name not in files:
        print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
        sys.exit(1)
    for name, path in files.items():
        _set_agent_default(path, name == args.agent_name)
    print(f"Default agent set to '{args.agent_name}'.")
