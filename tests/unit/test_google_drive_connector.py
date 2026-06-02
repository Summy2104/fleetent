from __future__ import annotations

import pytest


def test_google_drive_connector_config_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import GoogleDriveConnectorConfig

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
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
        FileCredentialRefResolver,
    )

    token_path = tmp_path / "google-token.json"
    token_path.write_text('{"refresh_token":"test"}', encoding="utf-8")
    resolver = FileCredentialRefResolver()

    credential = resolver.resolve(str(token_path))

    assert credential.credential_ref == str(token_path)
    assert credential.payload == '{"refresh_token":"test"}'


async def test_auth_failure_marks_summary_auth_failed():
    from fleetent.intelligence.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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


async def test_google_drive_listing_marks_supported_and_unsupported_mime_types():
    from fleetent.intelligence.knowledge_base import GoogleDriveConnectorConfig, SyncAction
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base import GoogleDriveConnectorConfig
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
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
    from fleetent.intelligence.knowledge_base.connectors import google_drive
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
        parse_google_drive_file,
    )
    from fleetent.intelligence.knowledge_base.parsers import ParsedDocument, ParsedSection

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
