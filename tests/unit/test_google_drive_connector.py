from __future__ import annotations

import json

import httpx
import pytest
import respx


def test_google_drive_connector_config_public_api_is_importable():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig

    config = GoogleDriveConnectorConfig(
        connector_id="gdrive-team",
        tenant_id="tenant-a",
        kb_id="support",
        folder_id="folder-1",
        credential_ref="file:///secure/google-token.json",
    )

    assert config.connector_id == "gdrive-team"
    assert config.tenant_id == "tenant-a"
    assert config.kb_id == "support"
    assert config.folder_id == "folder-1"
    assert config.credential_ref == "file:///secure/google-token.json"
    assert config.recursive is True


def test_file_credential_ref_resolver_supports_local_token_file(tmp_path):
    from fleetent.knowledge_base.connectors.google_drive import (
        FileCredentialRefResolver,
    )

    token_path = tmp_path / "google-token.json"
    token_path.write_text('{"refresh_token":"test"}', encoding="utf-8")
    resolver = FileCredentialRefResolver()

    credential = resolver.resolve(str(token_path))

    assert credential.credential_ref == str(token_path)
    assert credential.payload == '{"refresh_token":"test"}'


def test_google_drive_credential_ref_resolver_supports_env(monkeypatch):
    from fleetent.knowledge_base.connectors.google_drive import (
        CredentialRefResolver,
    )

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_TOKEN_JSON", '{"access_token":"env-token"}')
    resolver = CredentialRefResolver()

    credential = resolver.resolve("env:FLEETENT_GOOGLE_DRIVE_TOKEN_JSON")

    assert credential.credential_ref == "env:FLEETENT_GOOGLE_DRIVE_TOKEN_JSON"
    assert credential.payload == '{"access_token":"env-token"}'


def test_google_drive_credential_ref_resolver_supports_flat_env_prefix(monkeypatch):
    from fleetent.knowledge_base.connectors.google_drive import (
        CredentialRefResolver,
    )

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_CLIENT_ID", "client-id")
    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET", "client-secret")

    credential = CredentialRefResolver().resolve("env:FLEETENT_GOOGLE_DRIVE")

    payload = json.loads(credential.payload)
    assert payload == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_google_drive_credential_ref_resolver_prefers_explicit_env_mapping(monkeypatch):
    from fleetent.knowledge_base.connectors.google_drive import CredentialRefResolver

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_TOKEN_JSON", '{"access_token":"global-token"}')

    credential = CredentialRefResolver().resolve(
        "env:FLEETENT_GOOGLE_DRIVE_TOKEN_JSON",
        env={"FLEETENT_GOOGLE_DRIVE_TOKEN_JSON": '{"access_token":"tenant-token"}'},
    )

    assert credential.payload == '{"access_token":"tenant-token"}'


async def test_auth_failure_marks_summary_auth_failed():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        plan_google_drive_sync,
    )

    plan = await plan_google_drive_sync(
        GoogleDriveConnectorConfig(
            connector_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            folder_id="folder-1",
            credential_ref="file:///secure/google-token.json",
        ),
        client=FakeGoogleDriveClient(auth_failed=True),
    )

    assert plan.items == []
    assert plan.summary.auth_failed == 1
    assert plan.summary.failed == 1


def test_fake_drive_client_lists_only_requested_folder():
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
    )

    client = FakeGoogleDriveClient(
        files_by_folder={
            "folder-1": [
                GoogleDriveFile(
                    id="doc-1",
                    name="Runbook",
                    mime_type="application/vnd.google-apps.document",
                    modified_time="2026-06-02T00:00:00+00:00",
                    revision_id="rev-1",
                )
            ],
            "folder-2": [
                GoogleDriveFile(
                    id="doc-2",
                    name="Other",
                    mime_type="text/plain",
                    modified_time="2026-06-02T00:00:00+00:00",
                )
            ],
        }
    )

    assert [file.id for file in client.list_files("folder-1", recursive=True)] == ["doc-1"]


@respx.mock
def test_http_google_drive_client_lists_files_with_bearer_auth(tmp_path):
    from fleetent.knowledge_base.connectors.google_drive import (
        HttpGoogleDriveClient,
    )

    token_path = tmp_path / "google-token.json"
    token_path.write_text(json.dumps({"access_token": "drive-access"}), encoding="utf-8")
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "doc-1",
                        "name": "Runbook",
                        "mimeType": "text/markdown",
                        "modifiedTime": "2026-06-02T00:00:00.000Z",
                        "headRevisionId": "rev-1",
                        "webViewLink": "https://drive.google.com/file/d/doc-1/view",
                    }
                ]
            },
        )
    )

    files = HttpGoogleDriveClient(f"file://{token_path}").list_files(
        "folder-1",
        recursive=True,
    )

    assert [file.id for file in files] == ["doc-1"]
    assert files[0].mime_type == "text/markdown"
    assert files[0].revision_id == "rev-1"
    assert files[0].web_url == "https://drive.google.com/file/d/doc-1/view"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer drive-access"
    assert request.url.params["q"] == "'folder-1' in parents and trashed = false"
    assert request.url.params["supportsAllDrives"] == "true"
    assert request.url.params["includeItemsFromAllDrives"] == "true"


@respx.mock
def test_http_google_drive_client_accepts_env_credential_ref(monkeypatch):
    from fleetent.knowledge_base.connectors.google_drive import (
        HttpGoogleDriveClient,
    )

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_TOKEN_JSON", '{"access_token":"env-access"}')
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )

    files = HttpGoogleDriveClient("env:FLEETENT_GOOGLE_DRIVE_TOKEN_JSON").list_files(
        "folder-1",
        recursive=True,
    )

    assert files == []
    assert route.calls.last.request.headers["Authorization"] == "Bearer env-access"


@respx.mock
def test_http_google_drive_client_downloads_and_exports_files(tmp_path):
    from fleetent.knowledge_base.connectors.google_drive import (
        XLSX_MIME,
        HttpGoogleDriveClient,
    )

    token_path = tmp_path / "google-token.json"
    token_path.write_text(json.dumps({"access_token": "drive-access"}), encoding="utf-8")
    download_route = respx.get("https://www.googleapis.com/drive/v3/files/file-1").mock(
        return_value=httpx.Response(200, content=b"plain text")
    )
    export_route = respx.get("https://www.googleapis.com/drive/v3/files/sheet-1/export").mock(
        return_value=httpx.Response(200, content=b"xlsx bytes")
    )
    client = HttpGoogleDriveClient(f"file://{token_path}")

    assert client.download("file-1") == b"plain text"
    assert client.export("sheet-1", XLSX_MIME) == b"xlsx bytes"

    assert download_route.calls.last.request.url.params["alt"] == "media"
    assert export_route.calls.last.request.url.params["mimeType"] == XLSX_MIME


@respx.mock
def test_http_google_drive_client_refreshes_expired_oauth_token(tmp_path):
    from fleetent.knowledge_base.connectors.google_drive import (
        HttpGoogleDriveClient,
    )

    token_path = tmp_path / "google-token.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "expired-access",
                "refresh_token": "refresh-token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "token_uri": "https://oauth2.googleapis.com/token",
                "expiry": "2000-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    refresh_route = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600})
    )
    list_route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )

    files = HttpGoogleDriveClient(f"file://{token_path}").list_files("folder-1", recursive=True)

    assert files == []
    assert "refresh_token=refresh-token" in refresh_route.calls.last.request.content.decode()
    assert list_route.calls.last.request.headers["Authorization"] == "Bearer fresh-access"


async def test_google_drive_listing_marks_supported_and_unsupported_mime_types():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig, SyncAction
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        plan_google_drive_sync,
    )

    client = FakeGoogleDriveClient(
        files_by_folder={
            "folder-1": [
                GoogleDriveFile(
                    id="doc-1",
                    name="Runbook",
                    mime_type="application/vnd.google-apps.document",
                    modified_time="2026-06-02T00:00:00+00:00",
                    revision_id="rev-1",
                ),
                GoogleDriveFile(
                    id="sheet-1",
                    name="Budget",
                    mime_type="application/vnd.google-apps.spreadsheet",
                    modified_time="2026-06-02T00:00:00+00:00",
                ),
                GoogleDriveFile(
                    id="slide-1",
                    name="Deck",
                    mime_type="application/vnd.google-apps.presentation",
                    modified_time="2026-06-02T00:00:00+00:00",
                ),
            ]
        }
    )

    plan = await plan_google_drive_sync(
        GoogleDriveConnectorConfig(
            connector_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            folder_id="folder-1",
            credential_ref="token.json",
        ),
        client=client,
    )

    assert [item.action for item in plan.items] == [
        SyncAction.INGEST_NEW,
        SyncAction.INGEST_NEW,
        SyncAction.INGEST_NEW,
    ]
    assert [item.document_format for item in plan.items] == ["html", "xlsx", "pptx"]
    assert plan.summary.unsupported == 0


async def test_google_drive_malformed_file_metadata_is_counted_as_failed():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        plan_google_drive_sync,
    )

    plan = await plan_google_drive_sync(
        GoogleDriveConnectorConfig(
            connector_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            folder_id="folder-1",
            credential_ref="token.json",
        ),
        client=FakeGoogleDriveClient(
            files_by_folder={
                "folder-1": [
                    GoogleDriveFile(
                        id="bad-file",
                        name="Bad metadata",
                        mime_type="text/plain",
                        modified_time="not-a-timestamp",
                    )
                ]
            }
        ),
    )

    assert plan.items == []
    assert plan.summary.scanned == 1
    assert plan.summary.failed == 1


async def test_google_drive_export_or_download_failure_is_counted_per_item():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        execute_google_drive_sync_plan,
        plan_google_drive_sync,
    )

    client = FakeGoogleDriveClient(
        files_by_folder={
            "folder-1": [
                GoogleDriveFile(
                    id="doc-1",
                    name="Runbook",
                    mime_type="application/vnd.google-apps.document",
                    modified_time="2026-06-02T00:00:00+00:00",
                )
            ]
        },
        exports={},
    )
    config = GoogleDriveConnectorConfig(
        connector_id="gdrive-team",
        tenant_id="tenant-a",
        kb_id="support",
        folder_id="folder-1",
        credential_ref="token.json",
    )

    plan = await plan_google_drive_sync(config, client=client)
    summary = await execute_google_drive_sync_plan(plan, client=client)

    assert summary.planned == 1
    assert summary.ingested == 0
    assert summary.failed == 1


@pytest.mark.parametrize(
    ("filename", "mime_type", "expected_format"),
    [
        ("notes.txt", "text/plain", "text"),
        ("guide.md", "text/markdown", "markdown"),
        ("page.html", "text/html", "html"),
        ("README.md", "text/plain", "markdown"),
        ("Sheet", "application/vnd.google-apps.spreadsheet", "xlsx"),
        ("Slides", "application/vnd.google-apps.presentation", "pptx"),
        ("report.pdf", "application/pdf", "pdf"),
        (
            "guide.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "deck.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
        (
            "book.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        ),
    ],
)
def test_google_drive_format_detection(filename, mime_type, expected_format):
    from fleetent.knowledge_base.connectors.google_drive import (
        GoogleDriveFile,
        google_drive_document_format,
    )

    assert (
        google_drive_document_format(
            GoogleDriveFile(
                id="file-1",
                name=filename,
                mime_type=mime_type,
                modified_time="2026-06-02T00:00:00+00:00",
            )
        )
        == expected_format
    )


def test_google_drive_parser_dispatch_uses_export_or_download():
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        parse_google_drive_file,
    )

    docs_file = GoogleDriveFile(
        id="doc-1",
        name="Runbook",
        mime_type="application/vnd.google-apps.document",
        modified_time="2026-06-02T00:00:00+00:00",
    )
    markdown_file = GoogleDriveFile(
        id="md-1",
        name="guide.md",
        mime_type="text/markdown",
        modified_time="2026-06-02T00:00:00+00:00",
    )
    client = FakeGoogleDriveClient(
        exports={"doc-1": "<h1>Runbook</h1><p>Restart service</p>"},
        downloads={"md-1": b"# Guide\nRestart service"},
    )

    docs = parse_google_drive_file(client, docs_file)
    markdown = parse_google_drive_file(client, markdown_file)

    assert docs.format == "html"
    assert docs.sections[0].title == "Runbook"
    assert markdown.format == "markdown"
    assert markdown.sections[0].title == "Guide"


def test_google_drive_advanced_parser_dispatch_uses_registry(monkeypatch):
    from fleetent.knowledge_base.connectors import google_drive
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        parse_google_drive_file,
    )
    from fleetent.knowledge_base.parsers import ParsedDocument, ParsedSection

    calls = []

    def fake_parse_document(filename: str, content: bytes | str, mime_type: str | None = None):
        calls.append((filename, content, mime_type))
        return ParsedDocument(
            filename=filename,
            format=filename.rsplit(".", 1)[1],
            sections=[
                ParsedSection(
                    title="body",
                    text="advanced text",
                    level=0,
                    metadata={"path": "body"},
                )
            ],
            metadata={"filename": filename},
        )

    monkeypatch.setattr(google_drive, "parse_document", fake_parse_document)
    client = FakeGoogleDriveClient(
        exports={
            "sheet-1": b"xlsx export",
            "slide-1": b"pptx export",
        },
        downloads={
            "pdf-1": b"pdf bytes",
            "docx-1": b"docx bytes",
        },
    )

    sheet = parse_google_drive_file(
        client,
        GoogleDriveFile(
            id="sheet-1",
            name="Planning Sheet",
            mime_type="application/vnd.google-apps.spreadsheet",
            modified_time="2026-06-02T00:00:00+00:00",
        ),
    )
    slide = parse_google_drive_file(
        client,
        GoogleDriveFile(
            id="slide-1",
            name="Pilot Slides",
            mime_type="application/vnd.google-apps.presentation",
            modified_time="2026-06-02T00:00:00+00:00",
        ),
    )
    pdf = parse_google_drive_file(
        client,
        GoogleDriveFile(
            id="pdf-1",
            name="report.pdf",
            mime_type="application/pdf",
            modified_time="2026-06-02T00:00:00+00:00",
        ),
    )
    docx = parse_google_drive_file(
        client,
        GoogleDriveFile(
            id="docx-1",
            name="guide.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            modified_time="2026-06-02T00:00:00+00:00",
        ),
    )

    assert [sheet.format, slide.format, pdf.format, docx.format] == ["xlsx", "pptx", "pdf", "docx"]
    assert calls == [
        (
            "Planning Sheet.xlsx",
            b"xlsx export",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "Pilot Slides.pptx",
            b"pptx export",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("report.pdf", b"pdf bytes", "application/pdf"),
        (
            "guide.docx",
            b"docx bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]
