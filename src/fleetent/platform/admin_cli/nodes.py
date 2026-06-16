"""Admin CLI commands for node registry and placements."""

from __future__ import annotations

import argparse
import sys

from fleetent.platform.node_management import node_store, placement_store


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    node = subparsers.add_parser("node", help="Manage agent runtime nodes")
    node_subparsers = node.add_subparsers(dest="node_cmd", required=True)

    p_register = node_subparsers.add_parser("register", help="Register a node")
    p_register.add_argument("node_id")
    p_register.add_argument("--name")
    p_register.add_argument(
        "--label",
        action="append",
        default=[],
        help="Repeatable key=value label stored for future scheduling.",
    )

    node_subparsers.add_parser("list", help="List registered nodes")

    p_deregister = node_subparsers.add_parser("deregister", help="Deregister a node")
    p_deregister.add_argument("node_id")

    p_pin = node_subparsers.add_parser("pin", help="Pin an agent to a node")
    p_pin.add_argument("--agent-id", type=int, required=True)
    p_pin.add_argument("--node-id", required=True)
    p_pin.add_argument("--by", dest="pinned_by")

    p_unpin = node_subparsers.add_parser("unpin", help="Remove an agent placement")
    p_unpin.add_argument("--agent-id", type=int, required=True)


def handle(args: argparse.Namespace) -> bool:
    if args.cmd != "node":
        return False

    if args.node_cmd == "register":
        try:
            plaintext, node = node_store.register_node(
                args.node_id,
                name=args.name,
                labels=_parse_labels(args.label),
            )
        except ValueError as exc:
            _die(exc)
        print(f"Node {node['id']} registered.")
        print(f"  service_key: {plaintext}  <- save this, shown once")
        return True

    if args.node_cmd == "list":
        nodes = node_store.list_nodes()
        if not nodes:
            print("No nodes.")
            return True
        print(f"{'NODE ID':<20}  {'NAME':<20}  {'LABELS':<24}  LAST SEEN")
        for node in nodes:
            labels = ",".join(f"{key}={value}" for key, value in sorted(node["labels"].items()))
            last_seen = node["last_seen_at"] or "-"
            print(f"{node['id']:<20}  {(node['name'] or '-'): <20}  {labels:<24}  {last_seen}")
        return True

    if args.node_cmd == "deregister":
        try:
            node_store.deregister_node(args.node_id)
        except ValueError as exc:
            _die(exc)
        print(f"Node {args.node_id} deregistered.")
        return True

    if args.node_cmd == "pin":
        try:
            placement_store.pin_agent(args.agent_id, args.node_id, pinned_by=args.pinned_by)
        except ValueError as exc:
            _die(exc)
        print(f"Pinned agent {args.agent_id} to node {args.node_id}.")
        return True

    if args.node_cmd == "unpin":
        placement_store.unpin_agent(args.agent_id)
        print(f"Unpinned agent {args.agent_id}.")
        return True

    return False


def _parse_labels(raw_labels: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in raw_labels:
        if "=" not in item:
            raise ValueError(f"invalid label {item!r}; expected key=value")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError(f"invalid label {item!r}; key must not be empty")
        labels[key] = value
    return labels


def _die(exc: Exception) -> None:
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)
