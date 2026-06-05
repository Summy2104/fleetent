"""Unified IM module: identity, connector registry/config, manager, allowlist, admin API.

Single owner of IM persistence. Submodules:
  identity            — (platform, platform_user_id) → internal User + allowlist/workbench
  connector_store     — connector registry + status
  connector_config    — credential resolution (DB first, admin-owner env fallback), masked reads
  connector_manager   — async adapter supervisor (start/stop/reload)
  channel_allowlist   — per-owner channel/workspace allowlist enforcement
  admin_api           — /admin/im FastAPI router

Legacy top-level paths (fleetent.im_user_store, …im_gateway_management.im_*) remain as
re-export-only compatibility shims.
"""

from fleetent.platform.im_gateway_management.admin_api import router
from fleetent.platform.im_gateway_management.channel_allowlist import (
    add_entry,
    is_allowed,
    list_entries,
    remove_entry,
)
from fleetent.platform.im_gateway_management.connector_config import (
    resolve,
    resolve_masked,
    seed_from_env,
    set_config,
)
from fleetent.platform.im_gateway_management.connector_manager import ConnectorManager
from fleetent.platform.im_gateway_management.connector_store import (
    get_connector,
    heartbeat,
    list_connectors,
    report_status,
    set_allowlist_enforced,
    set_enabled,
    upsert_connector,
)
from fleetent.platform.im_gateway_management.identity import (
    DB_PATH,
    PLATFORM_IDENTITY_FIELDS,
    approve_user,
    block_im_user,
    check_allowed_by_user_id,
    delete_im_identity,
    disable_im_accounts,
    get_im_user,
    get_or_create,
    identity_fields,
    list_all,
    list_im_identities,
    list_pending,
    rebind_im_identity,
    restore_im_user,
    update_im_identity_metadata,
)

__all__ = [
    "DB_PATH",
    "PLATFORM_IDENTITY_FIELDS",
    "ConnectorManager",
    "add_entry",
    "approve_user",
    "block_im_user",
    "check_allowed_by_user_id",
    "delete_im_identity",
    "disable_im_accounts",
    "get_connector",
    "get_im_user",
    "get_or_create",
    "identity_fields",
    "heartbeat",
    "is_allowed",
    "list_all",
    "list_connectors",
    "list_entries",
    "list_im_identities",
    "list_pending",
    "rebind_im_identity",
    "remove_entry",
    "update_im_identity_metadata",
    "report_status",
    "resolve",
    "resolve_masked",
    "restore_im_user",
    "router",
    "seed_from_env",
    "set_allowlist_enforced",
    "set_config",
    "set_enabled",
    "upsert_connector",
]
