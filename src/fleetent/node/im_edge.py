from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Any

import httpx

from fleetent.db import SQLiteDatabase
from fleetent.identity import Principal, encode_ingress_principal
from fleetent.im_gateway import connector_registry, outbound_queue_store
from fleetent.im_gateway.access import IMIdentityResolutionError, set_im_identity_resolver
from fleetent.im_gateway.inbound_dispatch import set_inbound_dispatcher
from fleetent.im_gateway.normalizer import FileAttachment, NormalizedMessage
from fleetent.im_gateway.slack_supervisor import SlackSupervisor
from fleetent.im_gateway.telegram_supervisor import TelegramSupervisor
from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredState
from fleetent.structured_logging import get_logger

_logger = get_logger("node.im_edge")


def _extract_link_code(text: str) -> str | None:
    stripped = text.strip()
    if not stripped.startswith("/link"):
        return None
    parts = stripped.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return None
    return parts[1].strip()


class PlatformIdentityResolver:
    """Resolve IM identities for node-hosted connectors via the platform node API."""

    def __init__(self, config: NodeConfig) -> None:
        self._config = config
        self._tenant_by_agent: dict[str, str] = {}

    def update_agents(self, tenant_by_agent: dict[str, str]) -> None:
        self._tenant_by_agent = dict(tenant_by_agent)

    def __call__(self, owner_id: str, platform: str, platform_user_id: str) -> str:
        tenant_id = self._tenant_by_agent.get(owner_id)
        if tenant_id is None:
            raise IMIdentityResolutionError(f"unknown node-managed IM owner: {owner_id}")
        response = httpx.post(
            f"{self._config.platform_url}/nodes/{self._config.node_id}/identity/resolve",
            headers={"Authorization": f"Bearer {self._config.service_key}"},
            json={
                "tenant_id": tenant_id,
                "channel": platform,
                "platform_user_id": platform_user_id,
            },
            timeout=10.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IMIdentityResolutionError(str(exc)) from exc
        payload = dict(response.json())
        user_id = payload.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise IMIdentityResolutionError("platform identity response missing user_id")
        return user_id


class PlatformAddressResolver:
    """Reverse-lookup all IM addresses for a user_id via the platform node API.

    Called by node drain for user_id-targeted intents — agent never touches this directly.
    """

    def __init__(self, config: NodeConfig) -> None:
        self._config = config

    def resolve(self, user_id: str) -> list[dict[str, str]]:
        response = httpx.post(
            f"{self._config.platform_url}/nodes/{self._config.node_id}/identity/addresses",
            headers={"Authorization": f"Bearer {self._config.service_key}"},
            json={"user_id": user_id},
            timeout=10.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IMIdentityResolutionError(str(exc)) from exc
        payload = dict(response.json())
        addresses = payload.get("addresses", [])
        return [dict(a) for a in addresses if isinstance(a, dict)]


class NodeIMEdgeHost:
    """Own node-hosted IM supervisors and the injected managed identity resolver."""

    def __init__(
        self,
        config: NodeConfig,
        *,
        backend: BaseProcessBackend | None = None,
        slack_supervisor: SlackSupervisor | None = None,
        telegram_supervisor: TelegramSupervisor | None = None,
        resolver_setter: Callable[
            [Callable[[str, str, str], str] | None], None
        ] = set_im_identity_resolver,
        dispatcher_setter: Callable[
            [Callable[[NormalizedMessage], Any] | None], None
        ] = set_inbound_dispatcher,
    ) -> None:
        self._config = config
        self._backend = backend
        self._resolver = PlatformIdentityResolver(config)
        self._address_resolver = PlatformAddressResolver(config)
        self._resolver_setter = resolver_setter
        self._dispatcher_setter = dispatcher_setter
        self._slack_supervisor = slack_supervisor or SlackSupervisor()
        self._telegram_supervisor = telegram_supervisor or TelegramSupervisor()
        self._agent_db_paths: dict[str, Path] = {}
        self._dedup_path = config.home_dir / "node" / "im-outbound-dedup.json"
        self._sent_dedup_keys = self._load_dedup_keys()
        self._loop = asyncio.new_event_loop()
        self._drain_task: asyncio.Task[None] | None = None
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._run(self._start_background_tasks())
        self._resolver_setter(self._resolver)
        if backend is not None:
            self._dispatcher_setter(self._forward_inbound)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def reconcile(self, desired_state: DesiredState) -> None:
        tenant_by_agent: dict[str, str] = {}
        slack_bindings: dict[str, dict[str, str]] = {}
        telegram_bindings: dict[str, dict[str, str]] = {}
        agent_db_paths: dict[str, Path] = {}
        for agent in desired_state.agents:
            tenant_id = agent.tenant_id
            tenant_by_agent[agent.name] = tenant_id
            agent_db_paths[agent.name] = (
                self._config.home_dir
                / "tenants"
                / tenant_id
                / "agents"
                / agent.name
                / "data"
                / "agent_state.db"
            )
            im_config = dict(agent.config.get("im", {}))
            slack_binding = _materialize_slack_binding(im_config, agent.secrets)
            if slack_binding is not None:
                slack_bindings[agent.name] = slack_binding
            telegram_binding = _materialize_telegram_binding(im_config, agent.secrets)
            if telegram_binding is not None:
                telegram_bindings[agent.name] = telegram_binding
        self._resolver.update_agents(tenant_by_agent)
        self._agent_db_paths = agent_db_paths
        self._run(self._slack_supervisor.reload_bindings(slack_bindings))
        self._run(self._telegram_supervisor.reload_bindings(telegram_bindings))

    def close(self) -> None:
        try:
            self._run(self._stop_background_tasks())
            self._run(self._slack_supervisor.stop_all())
            self._run(self._telegram_supervisor.stop_all())
        finally:
            self._dispatcher_setter(None)
            self._resolver_setter(None)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def _run(self, awaitable: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(awaitable, self._loop)
        return future.result(timeout=10)

    async def _start_background_tasks(self) -> None:
        if self._drain_task is None:
            self._drain_task = asyncio.create_task(self._drain_loop())

    async def _stop_background_tasks(self) -> None:
        if self._drain_task is None:
            return
        self._drain_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._drain_task
        self._drain_task = None

    async def _drain_loop(self) -> None:
        while True:
            try:
                await self._drain_outbound_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
            await asyncio.sleep(self._config.interval_seconds)

    async def _drain_outbound_once(self) -> None:
        for agent_name, db_path in list(self._agent_db_paths.items()):
            if not db_path.exists():
                continue
            db = SQLiteDatabase(path=db_path)
            rows = outbound_queue_store.list_pending_with_db(db)
            connectors = connector_registry.snapshot(agent_name)
            for row in rows:
                await self._deliver_queue_row(agent_name, row, connectors, db)

    async def _deliver_queue_row(
        self,
        agent_name: str,
        row: dict[str, Any],
        connectors: dict[str, Any],
        db: SQLiteDatabase,
    ) -> None:
        from fleetent import outbound

        dedup_key = str(row.get("dedup_key", "") or "")
        if dedup_key and dedup_key in self._sent_dedup_keys:
            await self._mark_queue_sent(agent_name, row)
            return

        address = json.loads(str(row["address_json"]))
        payload = json.loads(str(row["payload_json"]))
        target_type = str(address.get("target_type", "user") or "user")

        if target_type == "user_id":
            await self._deliver_user_id_intent(agent_name, row, address, payload, connectors, db)
            return

        platform = str(row["platform"])
        target = str(address.get("target", ""))
        thread = address.get("thread")
        connector = connectors.get(platform)

        if payload.get("kind") == "file":
            receipt = await outbound.send_file_to(
                platform,
                connector,
                target,
                str(payload.get("path", "")),
                target_type=target_type,
                thread=thread,
            )
        else:
            blocks = payload.get("blocks") or None
            receipt = await outbound.send_to(
                platform,
                connector,
                target,
                str(payload.get("text", "")),
                target_type=target_type,
                thread=thread,
                blocks=blocks,
            )
        if not receipt.ok:
            outbound_queue_store.mark_failed_with_db(db, str(row["id"]))
            return

        if dedup_key:
            self._record_dedup_key(dedup_key)
        try:
            await self._mark_queue_sent(agent_name, row)
        except Exception:
            return

    async def _deliver_user_id_intent(
        self,
        agent_name: str,
        row: dict[str, Any],
        address: dict[str, Any],
        payload: dict[str, Any],
        connectors: dict[str, Any],
        db: SQLiteDatabase,
    ) -> None:
        from fleetent import outbound

        user_id = str(address.get("user_id", ""))
        text = str(payload.get("text", ""))
        blocks = payload.get("blocks") or None

        try:
            bindings = self._address_resolver.resolve(user_id)
        except Exception as exc:
            _logger.warn("directed_reach_address_lookup_failed", user_id=user_id, error=str(exc))
            outbound_queue_store.mark_failed_with_db(db, str(row["id"]))
            return

        if not bindings:
            _logger.info("directed_reach_no_bindings", user_id=user_id)
            await self._mark_queue_sent(agent_name, row)
            return

        for binding in bindings:
            plat = str(binding.get("platform", ""))
            puid = str(binding.get("platform_user_id", ""))
            connector = connectors.get(plat)
            try:
                await outbound.send_to(
                    plat, connector, puid, text, target_type="user", blocks=blocks
                )
            except Exception as exc:
                _logger.warn(
                    "directed_reach_channel_delivery_failed",
                    user_id=user_id,
                    platform=plat,
                    error=str(exc),
                )

        dedup_key = str(row.get("dedup_key", "") or "")
        if dedup_key:
            self._record_dedup_key(dedup_key)
        with contextlib.suppress(Exception):
            await self._mark_queue_sent(agent_name, row)

    async def _mark_queue_sent(self, agent_name: str, row: dict[str, Any]) -> None:
        db_path = self._agent_db_paths.get(agent_name)
        if db_path is None:
            return
        outbound_queue_store.mark_sent_with_db(SQLiteDatabase(path=db_path), str(row["id"]))

    def _load_dedup_keys(self) -> set[str]:
        if not self._dedup_path.exists():
            return set()
        payload = json.loads(self._dedup_path.read_text(encoding="utf-8"))
        return {str(item) for item in payload if isinstance(item, str)}

    def _record_dedup_key(self, dedup_key: str) -> None:
        if dedup_key in self._sent_dedup_keys:
            return
        self._sent_dedup_keys.add(dedup_key)
        self._dedup_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._dedup_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(sorted(self._sent_dedup_keys), ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._dedup_path)

    async def _forward_inbound(self, msg: NormalizedMessage) -> None:
        link_code = _extract_link_code(msg.text)
        if link_code is not None:
            await self._handle_link_command(msg, link_code)
            return
        if self._backend is None:
            raise RuntimeError("node IM dispatcher requires a backend")
        tenant_id = self._resolver._tenant_by_agent.get(msg.agent_name, "default")
        port = self._backend.gateway_port(msg.agent_name, tenant_id)
        if port is None:
            raise RuntimeError(f"agent {msg.agent_name!r} is unavailable")
        token = _agent_tui_token(self._config, msg.agent_name, tenant_id)
        principal = Principal(user_id=msg.user_id, tenant_id=tenant_id)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"http://127.0.0.1:{port}/im/route",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Fleetent-Principal": encode_ingress_principal(principal),
                },
                json=_serialize_message(msg),
            )
        response.raise_for_status()
        payload = dict(response.json())
        for reply in payload.get("replies", []):
            await _emit_reply(msg, dict(reply))

    async def _handle_link_command(self, msg: NormalizedMessage, code: str) -> None:
        sender_id = ""
        if msg.session_context is not None:
            sender_id = msg.session_context.sender_id
        if not sender_id:
            await msg.reply_func("Link failed: missing sender identity.")
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._config.platform_url}/nodes/{self._config.node_id}/link-confirm",
                headers={"Authorization": f"Bearer {self._config.service_key}"},
                json={
                    "platform": msg.platform,
                    "platform_user_id": sender_id,
                    "code": code,
                },
            )
        if response.status_code == 200:
            await msg.reply_func(f"Linked {msg.platform} account to your web identity.")
            return
        detail = "Link failed."
        with contextlib.suppress(Exception):
            payload = dict(response.json())
            raw_detail = payload.get("detail")
            if isinstance(raw_detail, str) and raw_detail:
                detail = f"Link failed: {raw_detail}"
        await msg.reply_func(detail)


def _materialize_slack_binding(
    im_config: dict[str, Any], secrets: dict[str, str]
) -> dict[str, str] | None:
    binding = im_config.get("slack")
    if not isinstance(binding, dict):
        return None
    bot_env = binding.get("bot_token_env")
    app_env = binding.get("app_token_env")
    if not isinstance(bot_env, str) or not isinstance(app_env, str):
        return None
    bot_token = secrets.get(bot_env)
    app_token = secrets.get(app_env)
    if not bot_token or not app_token:
        return None
    return {"bot_token": bot_token, "app_token": app_token}


def _materialize_telegram_binding(
    im_config: dict[str, Any], secrets: dict[str, str]
) -> dict[str, str] | None:
    binding = im_config.get("telegram")
    if not isinstance(binding, dict):
        return None
    bot_env = binding.get("bot_token_env")
    if not isinstance(bot_env, str):
        return None
    bot_token = secrets.get(bot_env)
    if not bot_token:
        return None
    return {"bot_token": bot_token}


def _agent_tui_token(config: NodeConfig, agent_name: str, tenant_id: str) -> str:
    env_path = config.home_dir / "tenants" / tenant_id / "agents" / agent_name / ".env"
    if not env_path.exists():
        raise RuntimeError(f"agent {agent_name!r} has no env scaffold")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("FLEETENT_TUI_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise RuntimeError(f"agent {agent_name!r} has no TUI token")


def _serialize_message(msg: NormalizedMessage) -> dict[str, Any]:
    return {
        "platform": msg.platform,
        "session_id": msg.session_id,
        "user_id": msg.user_id,
        "text": msg.text,
        "channel_id": msg.channel_id,
        "workspace_id": msg.workspace_id,
        "agent_name": msg.agent_name,
        "session_context": vars(msg.session_context) if msg.session_context is not None else None,
        "attachments": [_serialize_attachment(att) for att in msg.attachments],
    }


def _serialize_attachment(att: Any) -> dict[str, Any]:
    if isinstance(att, FileAttachment):
        return {
            "kind": "file",
            "data_b64": base64.b64encode(att.data).decode("ascii")
            if att.data is not None
            else None,
            "mime": att.mime,
            "filename": att.filename,
            "note": att.note,
        }
    if (
        isinstance(att, tuple)
        and len(att) == 2
        and isinstance(att[0], (bytes, bytearray))
        and isinstance(att[1], str)
    ):
        return {
            "kind": "image",
            "data_b64": base64.b64encode(bytes(att[0])).decode("ascii"),
            "mime": att[1],
        }
    raise TypeError(f"unsupported attachment: {type(att)!r}")


async def _emit_reply(msg: NormalizedMessage, reply: dict[str, Any]) -> None:
    text = str(reply.get("text", ""))
    blocks = reply.get("blocks")
    if msg.platform == "slack" and blocks is not None:
        await msg.reply_func(text, blocks)  # type: ignore[misc]
        return
    await msg.reply_func(text)
