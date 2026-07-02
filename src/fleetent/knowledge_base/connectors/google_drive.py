from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import httpx

from fleetent.knowledge_base import runtime
from fleetent.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.knowledge_base.parsers import (
    ParsedDocument,
    parse_document,
    parse_html,
    parse_markdown,
    parse_text,
)
from fleetent.knowledge_base.sync_planner import (
    SyncAction,
    SyncPlanItem,
    SyncPlanSummary,
)

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GOOGLE_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class GoogleDriveConnectorConfig:
    """Configuration for a Google Drive folder connector."""

    connector_id: str
    tenant_id: str
    kb_id: str
    folder_id: str
    credential_ref: str = ""
    recursive: bool = True
    access_token_env: str = ""
    refresh_token_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    token_uri_env: str = ""
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    supported_mime_types: tuple[str, ...] = (
        GOOGLE_DOC_MIME,
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/html",
        GOOGLE_SHEET_MIME,
        GOOGLE_SLIDE_MIME,
        "application/pdf",
        DOCX_MIME,
        PPTX_MIME,
        XLSX_MIME,
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

    def export(self, file_id: str, mime_type: str) -> bytes | str:
        """Export a Google-native file as the requested MIME type."""


class CredentialRefResolver:
    """Resolve env: and file/path credential_ref values for OAuth token payloads."""

    def resolve(
        self, credential_ref: str, env: Mapping[str, str] | None = None
    ) -> GoogleDriveCredential:
        source_env = env if env is not None else os.environ
        if credential_ref.startswith("env:"):
            env_name = credential_ref.removeprefix("env:")
            value = source_env.get(env_name)
            if value is None and _has_flat_env_credential(env_name, env=source_env):
                value = _flat_env_credential_payload(env_name, env=source_env)
            if value is None:
                raise GoogleDriveAuthError(f"missing credential env var: {env_name}")
            return GoogleDriveCredential(credential_ref=credential_ref, payload=value)
        path = _credential_path(credential_ref)
        return GoogleDriveCredential(
            credential_ref=credential_ref,
            payload=path.read_text(encoding="utf-8"),
        )


FileCredentialRefResolver = CredentialRefResolver


@dataclass
class HttpGoogleDriveClient:
    """Google Drive API client backed by OAuth token JSON."""

    credential_ref: str
    access_token_env: str = ""
    refresh_token_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    token_uri_env: str = ""
    env: Mapping[str, str] | None = None
    timeout_seconds: float = 20.0
    api_base_url: str = GOOGLE_DRIVE_API_BASE

    def list_files(self, folder_id: str, *, recursive: bool) -> list[GoogleDriveFile]:
        """List files visible in one configured folder."""
        files: list[GoogleDriveFile] = []
        folders_to_scan = [folder_id]
        seen_folders: set[str] = set()
        while folders_to_scan:
            current_folder = folders_to_scan.pop(0)
            if current_folder in seen_folders:
                continue
            seen_folders.add(current_folder)
            for item in self._list_folder_once(current_folder):
                if recursive and item.mime_type == GOOGLE_FOLDER_MIME:
                    folders_to_scan.append(item.id)
                    continue
                files.append(item)
        return files

    def download(self, file_id: str) -> bytes:
        """Download a binary/text file."""
        response = self._request(
            "GET",
            f"{self.api_base_url}/files/{file_id}",
            params={"alt": "media"},
        )
        return response.content

    def export(self, file_id: str, mime_type: str) -> bytes:
        """Export a Google-native file as the requested MIME type."""
        response = self._request(
            "GET",
            f"{self.api_base_url}/files/{file_id}/export",
            params={"mimeType": mime_type},
        )
        return response.content

    def _list_folder_once(self, folder_id: str) -> list[GoogleDriveFile]:
        page_token: str | None = None
        files: list[GoogleDriveFile] = []
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": (
                    "nextPageToken,files(id,name,mimeType,modifiedTime,headRevisionId,webViewLink)"
                ),
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            response = self._request("GET", f"{self.api_base_url}/files", params=params)
            body = response.json()
            if not isinstance(body, dict):
                raise RuntimeError("Google Drive list response is malformed")
            raw_files = body.get("files", [])
            if not isinstance(raw_files, list):
                raise RuntimeError("Google Drive files response is malformed")
            files.extend(_google_drive_files_from_json(raw_files))
            next_page = body.get("nextPageToken")
            if not isinstance(next_page, str) or not next_page:
                return files
            page_token = next_page

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {self._access_token()}"},
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Google Drive request failed: {exc}") from exc
        if response.status_code in {401, 403}:
            raise GoogleDriveAuthError("google drive authorization failed")
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Google Drive API returned status {response.status_code}")
        return response

    def _access_token(self) -> str:
        raw = _explicit_env_payload(
            access_token_env=self.access_token_env,
            refresh_token_env=self.refresh_token_env,
            client_id_env=self.client_id_env,
            client_secret_env=self.client_secret_env,
            token_uri_env=self.token_uri_env,
            env=self.env,
        )
        if raw is None:
            raw = CredentialRefResolver().resolve(self.credential_ref, env=self.env).payload
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GoogleDriveAuthError("google drive credential payload is invalid") from exc
        if not isinstance(payload, dict):
            raise GoogleDriveAuthError("google drive credential payload is invalid")

        access_token = payload.get("access_token")
        if isinstance(access_token, str) and access_token and not _token_expired(payload):
            return access_token
        if _can_refresh(payload):
            return _refresh_access_token(payload, timeout_seconds=self.timeout_seconds)
        if isinstance(access_token, str) and access_token:
            return access_token
        raise GoogleDriveAuthError("google drive access token is missing")


@dataclass
class FakeGoogleDriveClient:
    """Fake Drive client for deterministic connector tests."""

    files_by_folder: dict[str, list[GoogleDriveFile]] = field(default_factory=dict)
    downloads: dict[str, bytes] = field(default_factory=dict)
    exports: dict[str, bytes | str] = field(default_factory=dict)
    auth_failed: bool = False

    def list_files(self, folder_id: str, *, recursive: bool) -> list[GoogleDriveFile]:
        del recursive
        if self.auth_failed:
            raise GoogleDriveAuthError("google drive authorization failed")
        return list(self.files_by_folder.get(folder_id, []))

    def download(self, file_id: str) -> bytes:
        return self.downloads[file_id]

    def export(self, file_id: str, mime_type: str) -> bytes | str:
        if mime_type not in {"text/html", XLSX_MIME, PPTX_MIME}:
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
    failed = 0

    for file in files:
        try:
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
            failed=failed,
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
        return parse_html(
            _filename_for_file(file, "html"),
            _exported_text(client.export(file.id, "text/html")),
        )
    if file.mime_type == GOOGLE_SHEET_MIME:
        content = client.export(file.id, XLSX_MIME)
        return parse_document(_filename_for_file(file, "xlsx"), content, mime_type=XLSX_MIME)
    if file.mime_type == GOOGLE_SLIDE_MIME:
        content = client.export(file.id, PPTX_MIME)
        return parse_document(_filename_for_file(file, "pptx"), content, mime_type=PPTX_MIME)
    if document_format in {"pdf", "docx", "pptx", "xlsx"}:
        return parse_document(file.name, client.download(file.id), mime_type=file.mime_type)
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
    if file.mime_type == GOOGLE_SHEET_MIME:
        return "xlsx"
    if file.mime_type == GOOGLE_SLIDE_MIME:
        return "pptx"
    if file.mime_type == "text/plain":
        return "markdown" if name.endswith((".md", ".markdown")) else "text"
    if file.mime_type in {"text/markdown", "text/x-markdown"}:
        return "markdown"
    if file.mime_type == "text/html" or name.endswith((".html", ".htm")):
        return "html"
    if file.mime_type == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if file.mime_type == DOCX_MIME or name.endswith(".docx"):
        return "docx"
    if file.mime_type == PPTX_MIME or name.endswith(".pptx"):
        return "pptx"
    if file.mime_type == XLSX_MIME or name.endswith(".xlsx"):
        return "xlsx"
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
    if file.mime_type == GOOGLE_SHEET_MIME and not file.name.casefold().endswith(".xlsx"):
        return f"{file.name}.xlsx"
    if file.mime_type == GOOGLE_SLIDE_MIME and not file.name.casefold().endswith(".pptx"):
        return f"{file.name}.pptx"
    return file.name


def _exported_text(content: bytes | str) -> str:
    if isinstance(content, str):
        return content
    return content.decode("utf-8")


def _credential_path(credential_ref: str) -> Path:
    if credential_ref.startswith("file://"):
        return Path(credential_ref.removeprefix("file://")).expanduser()
    return Path(credential_ref).expanduser()


def _google_drive_files_from_json(raw_files: list[object]) -> list[GoogleDriveFile]:
    files: list[GoogleDriveFile] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise RuntimeError("Google Drive file metadata is malformed")
        file_id = raw_file.get("id")
        name = raw_file.get("name")
        mime_type = raw_file.get("mimeType")
        modified_time = raw_file.get("modifiedTime")
        if not isinstance(file_id, str) or not file_id:
            raise RuntimeError("Google Drive file metadata is malformed")
        if not isinstance(name, str) or not name:
            raise RuntimeError("Google Drive file metadata is malformed")
        if not isinstance(mime_type, str) or not mime_type:
            raise RuntimeError("Google Drive file metadata is malformed")
        if not isinstance(modified_time, str) or not modified_time:
            raise RuntimeError("Google Drive file metadata is malformed")
        revision_id = raw_file.get("headRevisionId")
        web_url = raw_file.get("webViewLink")
        files.append(
            GoogleDriveFile(
                id=file_id,
                name=name,
                mime_type=mime_type,
                modified_time=modified_time,
                revision_id=revision_id if isinstance(revision_id, str) else None,
                web_url=web_url if isinstance(web_url, str) else None,
            )
        )
    return files


def _token_expired(payload: dict[object, object]) -> bool:
    expiry = payload.get("expiry")
    if not isinstance(expiry, str) or not expiry:
        return False
    try:
        expires_at = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC) + timedelta(seconds=60)


def _can_refresh(payload: dict[object, object]) -> bool:
    return all(
        isinstance(payload.get(key), str) and payload.get(key)
        for key in ("refresh_token", "client_id", "client_secret")
    )


def _has_flat_env_credential(prefix: str, *, env: Mapping[str, str] | None = None) -> bool:
    source_env = env if env is not None else os.environ
    return any(
        source_env.get(f"{prefix}_{suffix}")
        for suffix in (
            "ACCESS_TOKEN",
            "REFRESH_TOKEN",
            "CLIENT_ID",
            "CLIENT_SECRET",
            "TOKEN_URI",
        )
    )


def _explicit_env_payload(
    *,
    access_token_env: str,
    refresh_token_env: str,
    client_id_env: str,
    client_secret_env: str,
    token_uri_env: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    source_env = env if env is not None else os.environ
    env_names = {
        "access_token": access_token_env,
        "refresh_token": refresh_token_env,
        "client_id": client_id_env,
        "client_secret": client_secret_env,
        "token_uri": token_uri_env,
    }
    if not any(env_names.values()):
        return None
    payload = {
        field: source_env.get(env_name, "")
        for field, env_name in env_names.items()
        if env_name and source_env.get(env_name)
    }
    if token_uri_env and "token_uri" not in payload:
        payload["token_uri"] = GOOGLE_TOKEN_URI
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _flat_env_credential_payload(prefix: str, *, env: Mapping[str, str] | None = None) -> str:
    source_env = env if env is not None else os.environ
    mapping = {
        "access_token": source_env.get(f"{prefix}_ACCESS_TOKEN", ""),
        "refresh_token": source_env.get(f"{prefix}_REFRESH_TOKEN", ""),
        "client_id": source_env.get(f"{prefix}_CLIENT_ID", ""),
        "client_secret": source_env.get(f"{prefix}_CLIENT_SECRET", ""),
        "token_uri": source_env.get(f"{prefix}_TOKEN_URI", GOOGLE_TOKEN_URI),
    }
    return json.dumps(
        {key: value for key, value in mapping.items() if value},
        ensure_ascii=False,
        sort_keys=True,
    )


def _refresh_access_token(payload: dict[object, object], *, timeout_seconds: float) -> str:
    token_uri = payload.get("token_uri")
    url = token_uri if isinstance(token_uri, str) and token_uri else GOOGLE_TOKEN_URI
    data = {
        "grant_type": "refresh_token",
        "refresh_token": str(payload["refresh_token"]),
        "client_id": str(payload["client_id"]),
        "client_secret": str(payload["client_secret"]),
    }
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise GoogleDriveAuthError("google drive token refresh failed") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise GoogleDriveAuthError("google drive token refresh failed")
    try:
        body = response.json()
    except ValueError as exc:
        raise GoogleDriveAuthError("google drive token refresh returned malformed JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
        raise GoogleDriveAuthError("google drive token refresh did not return an access token")
    return str(body["access_token"])


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
