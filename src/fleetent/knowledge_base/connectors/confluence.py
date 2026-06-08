from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urljoin

import httpx

from fleetent.knowledge_base import runtime
from fleetent.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.knowledge_base.parsers import ParsedDocument, parse_html
from fleetent.knowledge_base.sync_planner import (
    SyncAction,
    SyncPlanItem,
    SyncPlanSummary,
)

ConfluenceScopeType = Literal["space", "page"]
SleepFn = Callable[[float], Awaitable[None]]
_CONFLUENCE_EXPAND = "body.storage,version,space,ancestors,history.lastUpdated"


@dataclass(frozen=True)
class ConfluenceConnectorConfig:
    """Configuration for a Confluence Cloud connector."""

    connector_id: str
    tenant_id: str
    kb_id: str
    base_url: str
    username: str = ""
    credential_ref: str = ""
    scope_type: ConfluenceScopeType = "space"
    username_env: str = ""
    api_token_env: str = ""
    space_key: str | None = None
    page_id: str | None = None
    include_children: bool = False
    requests_per_minute: int = 60
    max_retries: int = 2


@dataclass(frozen=True)
class ConfluenceCredential:
    """Resolved Confluence Cloud API token credential."""

    credential_ref: str
    payload: str


@dataclass(frozen=True)
class ConfluencePage:
    """Confluence page metadata and storage HTML."""

    id: str
    title: str
    space_key: str
    storage_html: str
    version: int
    modified_time: str
    ancestors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfluenceSyncPlan:
    """Confluence sync plan produced before any KB write occurs."""

    config: ConfluenceConnectorConfig
    items: list[SyncPlanItem]
    pages: dict[str, ConfluencePage]
    summary: SyncPlanSummary


@dataclass(frozen=True)
class ConfluenceSyncSummary:
    """Counts returned after applying a Confluence sync plan."""

    scanned: int
    planned: int
    ingested: int = 0
    changed: int = 0
    unchanged: int = 0
    archived: int = 0
    failed: int = 0
    auth_failed: int = 0


class ConfluenceAuthError(RuntimeError):
    """Raised when Confluence credentials cannot be used."""


class ConfluenceRateLimitError(RuntimeError):
    """Raised for a retryable Confluence 429 response."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("confluence rate limited")
        self.retry_after_seconds = retry_after_seconds


class ConfluenceClient(Protocol):
    """Minimal Confluence Cloud client boundary used by the connector."""

    def list_space_pages(self, space_key: str) -> list[list[ConfluencePage]]:
        """Return paginated pages for one space."""

    def get_page(self, page_id: str) -> ConfluencePage:
        """Return one page."""

    def list_child_pages(self, page_id: str) -> list[ConfluencePage]:
        """Return descendant pages for one page."""


class CredentialRefResolver:
    """Resolve env: and file credential_ref values."""

    def resolve(self, credential_ref: str) -> ConfluenceCredential:
        if credential_ref.startswith("env:"):
            env_name = credential_ref.removeprefix("env:")
            value = os.getenv(env_name)
            if value is None:
                raise ConfluenceAuthError(f"missing credential env var: {env_name}")
            return ConfluenceCredential(credential_ref=credential_ref, payload=value)
        path = Path(credential_ref.removeprefix("file://")).expanduser()
        return ConfluenceCredential(
            credential_ref=credential_ref,
            payload=path.read_text(encoding="utf-8").strip(),
        )


@dataclass
class HttpConfluenceClient:
    """Confluence Cloud REST client using username + API token basic auth."""

    base_url: str
    username: str
    credential_ref: str
    timeout_seconds: float = 20.0

    def list_space_pages(self, space_key: str) -> list[list[ConfluencePage]]:
        """Return paginated pages for one space."""
        params = {
            "spaceKey": space_key,
            "type": "page",
            "limit": "50",
            "expand": _CONFLUENCE_EXPAND,
        }
        return self._list_paginated("/rest/api/content", params=params)

    def get_page(self, page_id: str) -> ConfluencePage:
        """Return one page."""
        response = self._request(
            "GET",
            f"/rest/api/content/{page_id}",
            params={"expand": _CONFLUENCE_EXPAND},
        )
        return _confluence_page_from_json(response.json())

    def list_child_pages(self, page_id: str) -> list[ConfluencePage]:
        """Return descendant pages for one page."""
        groups = self._list_paginated(
            f"/rest/api/content/{page_id}/child/page",
            params={"limit": "50", "expand": _CONFLUENCE_EXPAND},
        )
        return [page for group in groups for page in group]

    def _list_paginated(
        self,
        path_or_url: str,
        *,
        params: dict[str, str],
    ) -> list[list[ConfluencePage]]:
        groups: list[list[ConfluencePage]] = []
        next_path: str | None = path_or_url
        next_params: dict[str, str] | None = params
        while next_path:
            response = self._request("GET", next_path, params=next_params)
            body = response.json()
            if not isinstance(body, dict):
                raise RuntimeError("Confluence response is malformed")
            results = body.get("results", [])
            if not isinstance(results, list):
                raise RuntimeError("Confluence results response is malformed")
            groups.append([_confluence_page_from_json(item) for item in results])
            links = body.get("_links", {})
            next_link = links.get("next") if isinstance(links, dict) else None
            next_path = next_link if isinstance(next_link, str) and next_link else None
            next_params = None
        return groups

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = _confluence_url(self.base_url, path_or_url)
        token = CredentialRefResolver().resolve(self.credential_ref).payload
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    auth=(self.username, token),
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Confluence request failed: {exc}") from exc
        if response.status_code in {401, 403}:
            raise ConfluenceAuthError("confluence authorization failed")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                seconds = float(retry_after)
            except ValueError:
                seconds = 1.0
            raise ConfluenceRateLimitError(seconds)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Confluence API returned status {response.status_code}")
        return response


@dataclass
class FakeConfluenceClient:
    """Fake Confluence client for deterministic connector tests."""

    space_pages: dict[str, list[list[ConfluencePage]]] = field(default_factory=dict)
    pages_by_id: dict[str, ConfluencePage] = field(default_factory=dict)
    child_pages: dict[str, list[ConfluencePage]] = field(default_factory=dict)
    auth_failed: bool = False
    transient_errors: list[Exception] = field(default_factory=list)

    def list_space_pages(self, space_key: str) -> list[list[ConfluencePage]]:
        self._maybe_raise()
        if self.auth_failed:
            raise ConfluenceAuthError("confluence authorization failed")
        return list(self.space_pages.get(space_key, []))

    def get_page(self, page_id: str) -> ConfluencePage:
        self._maybe_raise()
        if self.auth_failed:
            raise ConfluenceAuthError("confluence authorization failed")
        return self.pages_by_id[page_id]

    def list_child_pages(self, page_id: str) -> list[ConfluencePage]:
        self._maybe_raise()
        if self.auth_failed:
            raise ConfluenceAuthError("confluence authorization failed")
        return list(self.child_pages.get(page_id, []))

    def _maybe_raise(self) -> None:
        if self.transient_errors:
            raise self.transient_errors.pop(0)


async def list_confluence_scope_pages(
    config: ConfluenceConnectorConfig,
    *,
    client: ConfluenceClient,
    sleep: SleepFn = asyncio.sleep,
) -> list[ConfluencePage]:
    """List pages for the configured Confluence scope with bounded retry."""
    return await _call_with_retry(config, lambda: _list_scope_once(config, client), sleep=sleep)


async def plan_confluence_sync(
    config: ConfluenceConnectorConfig,
    *,
    client: ConfluenceClient,
    sleep: SleepFn = asyncio.sleep,
) -> ConfluenceSyncPlan:
    """Plan Confluence sync without mutating KB state."""
    try:
        pages = await list_confluence_scope_pages(config, client=client, sleep=sleep)
    except ConfluenceAuthError:
        return ConfluenceSyncPlan(
            config=config,
            items=[],
            pages={},
            summary=SyncPlanSummary(scanned=0, planned=0, failed=1, auth_failed=1),
        )

    state_store = _state_store_or_none()
    existing_states = (
        {
            state.source_path: state
            for state in state_store.list_for_source(
                config.connector_id,
                config.tenant_id,
                config.kb_id,
            )
        }
        if state_store is not None
        else {}
    )
    seen_paths: set[str] = set()
    page_by_path: dict[str, ConfluencePage] = {}
    items: list[SyncPlanItem] = []
    failed = 0
    for page in pages:
        try:
            source_path = confluence_source_path(page)
            seen_paths.add(source_path)
            page_by_path[source_path] = page
            fingerprint = confluence_fingerprint(page)
            state = existing_states.get(source_path)
            action = _remote_action_for_state(state, _modified_time_ns(page), fingerprint)
            items.append(_plan_item(config, page, action, state))
        except Exception:
            failed += 1

    for state in existing_states.values():
        if state.source_path in seen_paths:
            continue
        items.append(
            SyncPlanItem(
                action=SyncAction.ARCHIVE_MISSING,
                source_id=state.source_id,
                tenant_id=state.tenant_id,
                kb_id=state.kb_id,
                source_path=state.source_path,
                filename=state.source_path.removeprefix("confluence://"),
                document_format="html",
                mtime_ns=state.mtime_ns,
                content_hash=state.content_hash,
                document_id=state.document_id,
            )
        )

    return ConfluenceSyncPlan(
        config=config,
        items=items,
        pages=page_by_path,
        summary=SyncPlanSummary(
            scanned=len(pages),
            planned=len(items),
            failed=failed,
            ingested=sum(1 for item in items if item.action is SyncAction.INGEST_NEW),
            changed=sum(1 for item in items if item.action is SyncAction.REINGEST_CHANGED),
            unchanged=sum(1 for item in items if item.action is SyncAction.SKIP_UNCHANGED),
            archived=sum(1 for item in items if item.action is SyncAction.ARCHIVE_MISSING),
        ),
    )


def parse_confluence_page(page: ConfluencePage) -> ParsedDocument:
    """Parse Confluence storage HTML with page metadata."""
    parsed = parse_html(_filename_for_page(page), page.storage_html)
    metadata = {
        **parsed.metadata,
        "page_id": page.id,
        "space_key": page.space_key,
        "version": str(page.version),
    }
    if page.ancestors:
        metadata["ancestor_path"] = " > ".join(page.ancestors)
    return ParsedDocument(
        filename=parsed.filename,
        format=parsed.format,
        sections=parsed.sections,
        metadata=metadata,
    )


async def execute_confluence_sync_plan(
    plan: ConfluenceSyncPlan,
    *,
    client: ConfluenceClient,
) -> ConfluenceSyncSummary:
    """Execute a Confluence sync plan, isolating failures to one item."""
    del client
    state_store = _state_store_or_none()
    ingested = 0
    changed = 0
    unchanged = 0
    archived = 0
    failed = plan.summary.failed
    auth_failed = plan.summary.auth_failed

    for item in plan.items:
        try:
            if item.action is SyncAction.SKIP_UNCHANGED:
                unchanged += 1
                continue
            if item.action is SyncAction.ARCHIVE_MISSING:
                if item.document_id is None:
                    raise ValueError("archive_missing plan item requires document_id")
                await runtime.archive(item.document_id)
                if state_store is not None:
                    state_store.delete(item.source_id, item.tenant_id, item.kb_id, item.source_path)
                archived += 1
                continue
            if item.action is SyncAction.REINGEST_CHANGED:
                if item.document_id is None:
                    raise ValueError("reingest_changed plan item requires document_id")
                await runtime.delete(item.document_id)
                changed += 1
            if item.action not in {SyncAction.INGEST_NEW, SyncAction.REINGEST_CHANGED}:
                raise ValueError(f"unsupported Confluence sync action: {item.action}")

            page = plan.pages[item.source_path]
            document = await runtime.ingest_parsed(
                parse_confluence_page(page),
                tenant_id=item.tenant_id,
                kb_id=item.kb_id,
                source=f"confluence:{item.source_id}",
                source_url=item.source_path,
            )
            if state_store is not None:
                if item.mtime_ns is None or item.content_hash is None:
                    raise ValueError("ingest plan item requires mtime_ns and content_hash")
                state_store.upsert(
                    LocalSourceState(
                        source_id=item.source_id,
                        tenant_id=item.tenant_id,
                        kb_id=item.kb_id,
                        source_path=item.source_path,
                        mtime_ns=item.mtime_ns,
                        content_hash=item.content_hash,
                        document_id=document.id,
                    )
                )
            ingested += 1
        except Exception:
            failed += 1

    return ConfluenceSyncSummary(
        scanned=plan.summary.scanned,
        planned=plan.summary.planned,
        ingested=ingested,
        changed=changed,
        unchanged=unchanged,
        archived=archived,
        failed=failed,
        auth_failed=auth_failed,
    )


async def sync_confluence(
    config: ConfluenceConnectorConfig,
    *,
    client: ConfluenceClient,
) -> ConfluenceSyncSummary:
    """Run a manual Confluence sync through planner and executor phases."""
    plan = await plan_confluence_sync(config, client=client)
    return await execute_confluence_sync_plan(plan, client=client)


def confluence_source_path(page: ConfluencePage) -> str:
    return f"confluence://{page.id}"


def confluence_fingerprint(page: ConfluencePage) -> str:
    raw = "|".join([page.id, str(page.version), page.modified_time])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _call_with_retry(
    config: ConfluenceConnectorConfig,
    operation: Callable[[], list[ConfluencePage]],
    *,
    sleep: SleepFn,
) -> list[ConfluencePage]:
    attempts = 0
    while True:
        try:
            return operation()
        except ConfluenceRateLimitError as exc:
            if attempts >= config.max_retries:
                raise
            attempts += 1
            await sleep(exc.retry_after_seconds)


def _list_scope_once(
    config: ConfluenceConnectorConfig,
    client: ConfluenceClient,
) -> list[ConfluencePage]:
    if config.scope_type == "space":
        if not config.space_key:
            raise ValueError("space scope requires space_key")
        pages: list[ConfluencePage] = []
        for page_group in client.list_space_pages(config.space_key):
            pages.extend(page_group)
        return pages
    if config.scope_type == "page":
        if not config.page_id:
            raise ValueError("page scope requires page_id")
        pages = [client.get_page(config.page_id)]
        if config.include_children:
            pages.extend(client.list_child_pages(config.page_id))
        return pages
    raise ValueError(f"unsupported Confluence scope_type: {config.scope_type}")


def _plan_item(
    config: ConfluenceConnectorConfig,
    page: ConfluencePage,
    action: SyncAction,
    state: LocalSourceState | None = None,
) -> SyncPlanItem:
    return SyncPlanItem(
        action=action,
        source_id=config.connector_id,
        tenant_id=config.tenant_id,
        kb_id=config.kb_id,
        source_path=confluence_source_path(page),
        filename=_filename_for_page(page),
        document_format="html",
        mtime_ns=_modified_time_ns(page),
        content_hash=confluence_fingerprint(page),
        document_id=state.document_id if state is not None else None,
    )


def _remote_action_for_state(
    state: LocalSourceState | None,
    mtime_ns: int,
    content_hash: str,
) -> SyncAction:
    if state is None:
        return SyncAction.INGEST_NEW
    if state.mtime_ns == mtime_ns and state.content_hash == content_hash:
        return SyncAction.SKIP_UNCHANGED
    return SyncAction.REINGEST_CHANGED


def _modified_time_ns(page: ConfluencePage) -> int:
    value = page.modified_time.replace("Z", "+00:00")
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)


def _filename_for_page(page: ConfluencePage) -> str:
    return f"{page.title}.html"


def _state_store_or_none() -> LocalSourceStateStore | None:
    try:
        database = runtime._database()
        row = database.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = :type AND name = :name
            """,
            {"type": "table", "name": "knowledge_source_states"},
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return LocalSourceStateStore(database)


def _confluence_url(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return urljoin(f"{base_url.rstrip('/')}/", path_or_url.lstrip("/"))


def _confluence_page_from_json(raw: object) -> ConfluencePage:
    if not isinstance(raw, dict):
        raise RuntimeError("Confluence page response is malformed")
    page_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(page_id, str) or not page_id:
        raise RuntimeError("Confluence page id is missing")
    if not isinstance(title, str) or not title:
        raise RuntimeError("Confluence page title is missing")

    space = raw.get("space", {})
    space_key = space.get("key") if isinstance(space, dict) else None
    if not isinstance(space_key, str) or not space_key:
        raise RuntimeError("Confluence page space key is missing")

    body = raw.get("body", {})
    storage = body.get("storage", {}) if isinstance(body, dict) else {}
    storage_html = storage.get("value") if isinstance(storage, dict) else None
    if not isinstance(storage_html, str):
        raise RuntimeError("Confluence page storage HTML is missing")

    version_body = raw.get("version", {})
    version = version_body.get("number") if isinstance(version_body, dict) else None
    if not isinstance(version, int):
        raise RuntimeError("Confluence page version is missing")

    modified_time = _confluence_modified_time(raw, version_body)
    ancestors = raw.get("ancestors", [])
    ancestor_titles = [
        str(item["title"])
        for item in ancestors
        if isinstance(item, dict) and isinstance(item.get("title"), str)
    ]
    return ConfluencePage(
        id=page_id,
        title=title,
        space_key=space_key,
        storage_html=storage_html,
        version=version,
        modified_time=modified_time,
        ancestors=ancestor_titles,
    )


def _confluence_modified_time(
    raw: dict[object, object],
    version_body: object,
) -> str:
    history = raw.get("history", {})
    if isinstance(history, dict):
        last_updated = history.get("lastUpdated", {})
        if isinstance(last_updated, dict) and isinstance(last_updated.get("when"), str):
            return str(last_updated["when"])
    if isinstance(version_body, dict) and isinstance(version_body.get("when"), str):
        return str(version_body["when"])
    raise RuntimeError("Confluence page modified time is missing")
