"""Admin CLI commands for tenancy provisioning."""

from __future__ import annotations

import argparse
import sys

from fleetent.platform.tenancy import store as tenancy_store


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_create = subparsers.add_parser("create-tenant", help="Create a new tenant (principal)")
    p_create.add_argument(
        "--id", dest="tenant_id", default=None, help="Tenant id (uuid if omitted)"
    )
    p_create.add_argument("--name", required=True, help="Tenant display name")

    p_list = subparsers.add_parser("list-tenants", help="List all tenants")  # noqa: F841

    p_team = subparsers.add_parser("create-team", help="Create a team under a tenant")
    p_team.add_argument("--id", dest="team_id", default=None, help="Team id (uuid if omitted)")
    p_team.add_argument("--tenant-id", required=True, help="Parent tenant id")
    p_team.add_argument("--name", required=True, help="Team display name")

    p_ut = subparsers.add_parser("set-user-tenant", help="Assign a user to a tenant")
    p_ut.add_argument("--user-id", required=True, help="User uuid")
    p_ut.add_argument("--tenant-id", required=True, help="Tenant id")

    p_ap = subparsers.add_parser("set-approver", help="Set approver_user_id on a tenant or team")
    p_ap.add_argument(
        "--type",
        dest="entity_type",
        required=True,
        choices=["tenant", "team"],
        help="Entity type: tenant or team",
    )
    p_ap.add_argument("--id", dest="entity_id", required=True, help="Entity id")
    p_ap.add_argument("--user-id", required=True, help="Approver user uuid")


def handle(args: argparse.Namespace) -> bool:  # noqa: C901
    if args.cmd == "create-tenant":
        tenant = tenancy_store.create_tenant(id=args.tenant_id, name=args.name)
        print("Tenant created.")
        print(f"  id:     {tenant['id']}")
        print(f"  name:   {tenant['name']}")
        print(f"  status: {tenant['status']}")
        return True

    if args.cmd == "list-tenants":
        tenants = tenancy_store.list_tenants()
        if not tenants:
            print("No tenants.")
            return True
        print(f"{'ID':<36}  {'NAME':<24}  STATUS")
        for t in tenants:
            print(f"{t['id']:<36}  {t['name']:<24}  {t['status']}")
        return True

    if args.cmd == "create-team":
        try:
            team = tenancy_store.create_team(
                id=args.team_id, tenant_id=args.tenant_id, name=args.name
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print("Team created.")
        print(f"  id:        {team['id']}")
        print(f"  tenant_id: {team['tenant_id']}")
        print(f"  name:      {team['name']}")
        return True

    if args.cmd == "set-user-tenant":
        try:
            tenancy_store.set_user_tenant(args.user_id, args.tenant_id)
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"User {args.user_id!r} assigned to tenant {args.tenant_id!r}.")
        return True

    if args.cmd == "set-approver":
        if args.entity_type == "tenant":
            tenancy_store.set_tenant_approver(args.entity_id, args.user_id)
        else:
            tenancy_store.set_team_approver(args.entity_id, args.user_id)
        print(
            f"{args.entity_type.capitalize()} {args.entity_id!r} approver set to {args.user_id!r}."
        )
        return True

    return False
