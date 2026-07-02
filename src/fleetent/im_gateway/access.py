"""Agent-local IM access: approval store, identity resolution, and access gates.

Runtime-side (not platform) IM access for a self-contained agent. The static allow
rules live in the connector's `access` block in `agent.yaml`, parsed by
:mod:`fleetent.agent_config`; dynamic approvals live in a JSON store under the agent
home `data/`. All evaluation here is local — no platform-DB read — so a standalone agent
enforces its own access without a platform database (see openspec change
``per-agent-im-access``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from fleetent import paths
from fleetent.agent_config import ImAccess

if TYPE_CHECKING:
    from fleetent.identity import Principal

# Default agent-local approval store path (single-agent home). Injectable: the standalone
# agent runtime points this at its own home `data/`; tests pass an explicit path.
APPROVALS_PATH = paths.data_dir() / "im_approvals.json"

# Injectable hook for resolving an inbound IM identity to a platform user id.
# The platform server may wire this to platform-owned identity mapping code that reads
# and writes management tables; standalone agent runtime leaves it unset and therefore
# preserves native channel-id passthrough semantics.
_im_identity_resolver: Callable[[str, str, str], str] | None = None

# Injectable hook for reverse-resolving an internal user_id to its bound IM addresses
# (directed-reach). Standalone leaves it unset (no im_users) → resolves to empty. Managed
# wires an AgentAddressResolver that queries platform via the node loopback.
_im_address_resolver: Callable[[str], list[dict[str, str]]] | None = None

# Injectable hook for confirming an inbound ``/link <code>`` command (agent-hosted-im). Managed
# wires an AgentLinkConfirmer (node loopback → platform link-confirm); standalone leaves it unset
# so ``/link`` is not applicable (no node/platform to confirm against) → confirm_link returns None.
_im_link_confirmer: Callable[[str, str, str], tuple[bool, str]] | None = None


class IMIdentityResolutionError(RuntimeError):
    """Injected platform-side identity resolution rejected an inbound IM identity."""


class AgentIdentityResolver:
    """Managed agent-side identity resolver: platform_user_id → internal user_id via node
    loopback (agent-hosted-im). Authenticates to node with the agent's own TUI token; node
    forwards to platform holding the service key. No platform import, no service key held.
    """

    def __init__(
        self, *, loopback_url: str, tui_token: str, agent_name: str, tenant_id: str = "default"
    ) -> None:
        self._loopback_url = loopback_url.rstrip("/")
        self._tui_token = tui_token
        self._agent_name = agent_name
        self._tenant_id = tenant_id

    def __call__(self, owner_id: str, platform: str, platform_user_id: str) -> str:
        import httpx

        resp = httpx.post(
            f"{self._loopback_url}/agent/{self._agent_name}/identity/resolve",
            headers={"Authorization": f"Bearer {self._tui_token}"},
            json={
                "tenant_id": self._tenant_id,
                "channel": platform,
                "platform_user_id": platform_user_id,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        user_id = dict(resp.json()).get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise IMIdentityResolutionError("loopback identity response missing user_id")
        return user_id


class AgentAddressResolver:
    """Managed agent-side reverse address resolver: user_id → [(platform, platform_user_id)]
    via node loopback (agent-hosted-im), for directed-reach fan-out."""

    def __init__(self, *, loopback_url: str, tui_token: str, agent_name: str) -> None:
        self._loopback_url = loopback_url.rstrip("/")
        self._tui_token = tui_token
        self._agent_name = agent_name

    def resolve(self, user_id: str) -> list[dict[str, str]]:
        import httpx

        resp = httpx.post(
            f"{self._loopback_url}/agent/{self._agent_name}/identity/addresses",
            headers={"Authorization": f"Bearer {self._tui_token}"},
            json={"user_id": user_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        addresses = dict(resp.json()).get("addresses", [])
        return [dict(a) for a in addresses if isinstance(a, dict)]

    def __call__(self, user_id: str) -> list[dict[str, str]]:
        return self.resolve(user_id)


class AgentLinkConfirmer:
    """Managed agent-side ``/link`` confirmer: confirm an IM account linkage via node loopback
    (agent-hosted-im). The agent self-hosts its IM connection and handles the inbound
    ``/link <code>`` command in-process, proxying the confirmation through the node loopback with
    its own TUI token; node forwards to platform holding the service key. No platform import.
    """

    def __init__(self, *, loopback_url: str, tui_token: str, agent_name: str) -> None:
        self._loopback_url = loopback_url.rstrip("/")
        self._tui_token = tui_token
        self._agent_name = agent_name

    def confirm(self, platform: str, platform_user_id: str, code: str) -> tuple[bool, str]:
        """Confirm the link code, returning ``(ok, detail)``; never raises (best-effort)."""
        import httpx

        try:
            resp = httpx.post(
                f"{self._loopback_url}/agent/{self._agent_name}/link-confirm",
                headers={"Authorization": f"Bearer {self._tui_token}"},
                json={"platform": platform, "platform_user_id": platform_user_id, "code": code},
                timeout=10.0,
            )
        except Exception as exc:  # noqa: BLE001 — surface a clean failure detail, never raise
            return (False, str(exc))
        if resp.status_code == 200:
            return (True, "")
        detail = "Link failed."
        try:
            raw = dict(resp.json()).get("detail")
            if isinstance(raw, str) and raw:
                detail = f"Link failed: {raw}"
        except Exception:  # noqa: BLE001 — non-JSON error body → generic detail
            pass
        return (False, detail)

    def __call__(self, platform: str, platform_user_id: str, code: str) -> tuple[bool, str]:
        return self.confirm(platform, platform_user_id, code)


class LocalApprovalStore:
    """JSON-backed per-agent IM approval store under the agent home `data/`.

    Records IM-user identities as ``pending`` (awaiting approval) or ``approved``.
    Reads and writes are file-local; no platform database is touched. Writes are atomic
    (`.tmp → replace`), mirroring :mod:`fleetent.session.manager`.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _read(self) -> dict[str, list[str]]:
        if not self._path.exists():
            return {"pending": [], "approved": []}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {"pending": list(raw.get("pending", [])), "approved": list(raw.get("approved", []))}

    def _write(self, state: dict[str, list[str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def add_pending(self, identity: str) -> None:
        state = self._read()
        if identity not in state["pending"] and identity not in state["approved"]:
            state["pending"].append(identity)
            self._write(state)

    def approve(self, identity: str) -> None:
        state = self._read()
        if identity in state["pending"]:
            state["pending"].remove(identity)
        if identity not in state["approved"]:
            state["approved"].append(identity)
        self._write(state)

    def is_approved(self, identity: str) -> bool:
        return identity in self._read()["approved"]

    def list_approved(self) -> list[str]:
        return self._read()["approved"]

    def list_pending(self) -> list[str]:
        return self._read()["pending"]


def set_im_identity_resolver(resolver: Callable[[str, str, str], str] | None) -> None:
    """Wire the platform-owned IM identity resolver into the agent-side gateway module.

    The injected resolver belongs to platform startup code and may read/write platform
    identity tables. Agent-runtime code must not depend on its implementation details or
    on any platform schema.
    """
    global _im_identity_resolver
    _im_identity_resolver = resolver


def set_im_address_resolver(resolver: Callable[[str], list[dict[str, str]]] | None) -> None:
    """Wire the reverse address resolver (user_id → IM addresses) for directed-reach.

    Managed wires an :class:`AgentAddressResolver` (node loopback); standalone leaves it
    unset so :func:`resolve_addresses` returns empty (no im_users to reverse-lookup).
    """
    global _im_address_resolver
    _im_address_resolver = resolver


def resolve_addresses(user_id: str) -> list[dict[str, str]]:
    """Reverse-resolve a user_id to its bound IM addresses, or [] when unresolvable."""
    if _im_address_resolver is None:
        return []
    return _im_address_resolver(user_id)


def set_im_link_confirmer(
    confirmer: Callable[[str, str, str], tuple[bool, str]] | None,
) -> None:
    """Wire the ``/link`` confirmer (agent-hosted-im). Managed wires an
    :class:`AgentLinkConfirmer` (node loopback); standalone leaves it unset."""
    global _im_link_confirmer
    _im_link_confirmer = confirmer


def confirm_link_available() -> bool:
    """Whether a ``/link`` confirmer is wired (managed). Standalone → False (not applicable)."""
    return _im_link_confirmer is not None


def confirm_link(platform: str, platform_user_id: str, code: str) -> tuple[bool, str] | None:
    """Confirm an inbound ``/link <code>`` linkage, or ``None`` when not applicable (standalone).

    Returns ``(ok, detail)`` when a confirmer is wired (managed): ``ok`` is whether the linkage
    succeeded and ``detail`` a human-readable failure reason (empty on success).
    """
    if _im_link_confirmer is None:
        return None
    return _im_link_confirmer(platform, platform_user_id, code)


# AAA-8204 #1: non-real IM identities that must never be resolved/provisioned. A broken
# Slack assistant-thread context yields no user; a caller that fabricates one of these would
# otherwise make the injected resolver auto-create a ghost user (e.g. ``slack:unknown``) that
# then fails the access gate and blocks the real, authorized user at random.
_NON_REAL_IM_IDENTITIES = frozenset({"", "unknown"})


def resolve_identity(platform: str, platform_user_id: str, owner_id: str = "default") -> str:
    """Resolve a stable per-agent identity for an incoming IM message — no platform DB.

    The agent runtime uses the platform-native IM user id directly as the identity, so
    it never reads the platform ``user_store``. Author-facing ``allow_users`` entries in
    the binding's access block are matched against this same native id.

    Raises ``IMIdentityResolutionError`` for a non-real id (empty / ``unknown``) BEFORE the
    injected resolver runs, so no ghost user is ever provisioned; the caller must discard the
    event with a warning rather than fabricate an identity (AAA-8204 #1).
    """
    if (platform_user_id or "").strip().lower() in _NON_REAL_IM_IDENTITIES:
        raise IMIdentityResolutionError(f"non-real IM identity: {platform_user_id!r}")
    if _im_identity_resolver is not None:
        return _im_identity_resolver(owner_id, platform, platform_user_id)
    return platform_user_id


def resolve_principal(
    platform: str,
    platform_user_id: str,
    tenant_id: str = "default",
    owner_id: str = "default",
) -> Principal:
    """Wrap an IM channel-guaranteed identity as a Principal.

    Trusts the channel: the native IM user id becomes user_id with no user_store read.
    The tenant_id is supplied by the connector's edge configuration.
    """
    from fleetent.identity import Principal  # noqa: PLC0415

    return Principal(
        user_id=resolve_identity(platform, platform_user_id, owner_id=owner_id),
        tenant_id=tenant_id,
    )


def channel_allowed(access: ImAccess, channel_id: str) -> bool:
    """Group gate: only explicitly allowlisted groups are admitted."""
    if not access.allow_groups:
        return False
    return channel_id in access.allow_groups


def user_allowed(access: ImAccess, store: LocalApprovalStore, identity: str) -> bool:
    """User gate: allowed if statically listed or locally approved."""
    return identity in access.allow_users or store.is_approved(identity)
