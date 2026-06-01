from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fleetent.intelligence.knowledge_base import runtime
from fleetent.intelligence.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    parse_html,
    parse_markdown,
    parse_text,
)
from fleetent.intelligence.knowledge_base.sync_planner import (
    SyncAction,
    SyncPlanItem,
    SyncPlanSummary,
)

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"


@dataclass(frozen=True)
class GoogleDriveConnectorConfig:
    """Configuration for a Google Drive folder connector."""

    connector_id: str
    tenant_id: str
    kb_id: str
    folder_id: str
    credential_ref: str
    recursive: bool = True
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    supported_mime_types: tuple[str, ...] = (
        GOOGLE_DOC_MIME,
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/html",
    )


@dataclass(frozen=True)
class GoogleDriveCredential:
    """Resolved Google Drive OAuth credential payload."""

    credential_ref: str
    payload: str


@dataclass(frozen=True)
class GoogleDriveFile:
    """Metadata for one Google Drive file returned by a connector client."""

    id: str
    name: str
    mime_type: str
    modified_time: str
    revision_id: str | None = None
    web_url: str | None = None


@dataclass(frozen=True)
class GoogleDriveSyncPlan:
    """Google Drive sync plan produced before any KB write occurs."""

    config: GoogleDriveConnectorConfig
    items: list[SyncPlanItem]
    files: dict[str, GoogleDriveFile]
    summary: SyncPlanSummary


@dataclass(frozen=True)
class GoogleDriveSyncSummary:
    """Counts returned after applying a Google Drive sync plan."""

    scanned: int
    planned: int
    ingested: int = 0
    changed: int = 0
    unchanged: int = 0
    unsupported: int = 0
    archived: int = 0
    failed: int = 0
    auth_failed: int = 0


class GoogleDriveAuthError(RuntimeError):
    """Raised when Google Drive OAuth credentials cannot be used."""


class GoogleDriveClient(Protocol):
    """Minimal Google Drive client boundary used by the connector."""

    def list_files(self, folder_id: str, *, recursive: bool) -> list[GoogleDriveFile]:
        """List files visible in one configured folder."""

    def download(self, file_id: str) -> bytes:
        """Download a binary/text file."""

    def export(self, file_id: str, mime_type: str) -> str:
        """Export a Google-native file as the requested MIME type."""


class FileCredentialRefResolver:
    """Resolve file-based credential_ref values for OAuth token payloads."""

    def resolve(self, credential_ref: str) -> GoogleDriveCredential:
        path = _credential_path(credential_ref)
        return GoogleDriveCredential(
            credential_ref=credential_ref,
            payload=path.read_text(encoding="utf-8"),
        )


@dataclass
class FakeGoogleDriveClient:
    """Fake Drive client for deterministic connector tests."""

    files_by_folder: dict[str, list[GoogleDriveFile]] = field(default_factory=dict)
    downloads: dict[str, bytes] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    auth_failed: bool = False

    def list_files(self, folder_id: str, *, recursive: bool) -> list[GoogleDriveFile]:
        del recursive
        if self.auth_failed:
            raise GoogleDriveAuthError("google drive authorization failed")
        return list(self.files_by_folder.get(folder_id, []))

    def download(self, file_id: str) -> bytes:
        return self.downloads[file_id]

    def export(self, file_id: str, mime_type: str) -> str:
        if mime_type != "text/html":
            raise ValueError(f"unsupported export MIME type: {mime_type}")
        return self.exports[file_id]


async def plan_google_drive_sync(
    config: GoogleDriveConnectorConfig,
    *,
    client: GoogleDriveClient,
) -> GoogleDriveSyncPlan:
    """Plan Google Drive folder sync without mutating KB state."""
    try:
        files = client.list_files(config.folder_id, recursive=config.recursive)
    except GoogleDriveAuthError:
        return GoogleDriveSyncPlan(
            config=config,
            items=[],
            files={},
            summary=SyncPlanSummary(
                scanned=0,
                planned=0,
                failed=1,
                auth_failed=1,
            ),
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
    items: list[SyncPlanItem] = []
    file_by_path: dict[str, GoogleDriveFile] = {}

    for file in files:
        source_path = google_drive_source_path(file)
        seen_paths.add(source_path)
        file_by_path[source_path] = file
        document_format = google_drive_document_format(file)
        if document_format is None:
            items.append(_plan_item(config, file, SyncAction.SKIP_UNSUPPORTED, ""))
            continue
        fingerprint = google_drive_fingerprint(file)
        state = existing_states.get(source_path)
        action = _remote_action_for_state(state, _modified_time_ns(file), fingerprint)
        items.append(_plan_item(config, file, action, document_format, state))

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
                filename=state.source_path.removeprefix("drive://"),
                document_format="",
                mtime_ns=state.mtime_ns,
                content_hash=state.content_hash,
                document_id=state.document_id,
            )
        )

    return GoogleDriveSyncPlan(
        config=config,
        items=items,
        files=file_by_path,
        summary=SyncPlanSummary(
            scanned=len(files),
            planned=len(items),
            ingested=sum(1 for item in items if item.action is SyncAction.INGEST_NEW),
            changed=sum(1 for item in items if item.action is SyncAction.REINGEST_CHANGED),
            unchanged=sum(1 for item in items if item.action is SyncAction.SKIP_UNCHANGED),
            unsupported=sum(1 for item in items if item.action is SyncAction.SKIP_UNSUPPORTED),
            archived=sum(1 for item in items if item.action is SyncAction.ARCHIVE_MISSING),
        ),
    )


def parse_google_drive_file(
    client: GoogleDriveClient,
    file: GoogleDriveFile,
) -> ParsedDocument:
    """Fetch/export and parse one supported Google Drive file."""
    document_format = google_drive_document_format(file)
    if document_format is None:
        raise ValueError(f"unsupported Google Drive MIME type: {file.mime_type}")
    if file.mime_type == GOOGLE_DOC_MIME:
        return parse_html(_filename_for_file(file, "html"), client.export(file.id, "text/html"))
    content = client.download(file.id).decode("utf-8")
    if document_format == "text":
        return parse_text(file.name, content)
    if document_format == "markdown":
        return parse_markdown(file.name, content)
    if document_format == "html":
        return parse_html(file.name, content)
    raise ValueError(f"unsupported Google Drive document format: {document_format}")


async def execute_google_drive_sync_plan(
    plan: GoogleDriveSyncPlan,
    *,
    client: GoogleDriveClient,
) -> GoogleDriveSyncSummary:
    """Execute a Google Drive sync plan, isolating failures to one item."""
    state_store = _state_store_or_none()
    ingested = 0
    changed = 0
    unchanged = 0
    unsupported = 0
    archived = 0
    failed = plan.summary.failed
    auth_failed = plan.summary.auth_failed

    for item in plan.items:
        try:
            if item.action is SyncAction.SKIP_UNCHANGED:
                unchanged += 1
                continue
            if item.action is SyncAction.SKIP_UNSUPPORTED:
                unsupported += 1
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
                raise ValueError(f"unsupported Google Drive sync action: {item.action}")

            file = plan.files[item.source_path]
            parsed = parse_google_drive_file(client, file)
            document = await runtime.ingest_parsed(
                parsed,
                tenant_id=item.tenant_id,
                kb_id=item.kb_id,
                source=f"google_drive:{item.source_id}",
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

    return GoogleDriveSyncSummary(
        scanned=plan.summary.scanned,
        planned=plan.summary.planned,
        ingested=ingested,
        changed=changed,
        unchanged=unchanged,
        unsupported=unsupported,
        archived=archived,
        failed=failed,
        auth_failed=auth_failed,
    )


async def sync_google_drive(
    config: GoogleDriveConnectorConfig,
    *,
    client: GoogleDriveClient,
) -> GoogleDriveSyncSummary:
    """Run a manual Google Drive sync through planner and executor phases."""
    plan = await plan_google_drive_sync(config, client=client)
    return await execute_google_drive_sync_plan(plan, client=client)


def google_drive_document_format(file: GoogleDriveFile) -> str | None:
    """Map a Google Drive MIME type and filename to an existing parser format."""
    name = file.name.casefold()
    if file.mime_type == GOOGLE_DOC_MIME:
        return "html"
    if file.mime_type == "text/plain":
        return "markdown" if name.endswith((".md", ".markdown")) else "text"
    if file.mime_type in {"text/markdown", "text/x-markdown"}:
        return "markdown"
    if file.mime_type == "text/html" or name.endswith((".html", ".htm")):
        return "html"
    return None


def google_drive_source_path(file: GoogleDriveFile) -> str:
    """Stable remote source path used by the sync planner."""
    return f"drive://{file.id}"


def google_drive_fingerprint(file: GoogleDriveFile) -> str:
    """Deterministic remote metadata fingerprint used for changed detection."""
    raw = "|".join([file.id, file.modified_time, file.revision_id or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _plan_item(
    config: GoogleDriveConnectorConfig,
    file: GoogleDriveFile,
    action: SyncAction,
    document_format: str,
    state: LocalSourceState | None = None,
) -> SyncPlanItem:
    return SyncPlanItem(
        action=action,
        source_id=config.connector_id,
        tenant_id=config.tenant_id,
        kb_id=config.kb_id,
        source_path=google_drive_source_path(file),
        filename=_filename_for_file(file, document_format),
        document_format=document_format,
        mtime_ns=_modified_time_ns(file),
        content_hash=google_drive_fingerprint(file),
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


def _modified_time_ns(file: GoogleDriveFile) -> int:
    value = file.modified_time.replace("Z", "+00:00")
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)


def _filename_for_file(file: GoogleDriveFile, document_format: str) -> str:
    if file.mime_type == GOOGLE_DOC_MIME and not file.name.casefold().endswith(".html"):
        return f"{file.name}.html"
    return file.name


def _credential_path(credential_ref: str) -> Path:
    if credential_ref.startswith("file://"):
        return Path(credential_ref.removeprefix("file://")).expanduser()
    return Path(credential_ref).expanduser()


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
