from __future__ import annotations

from dataclasses import dataclass

import pytest

from fleetent.knowledge_base.config import KnowledgeConfigSnapshot


def _settings(**knowledge_base: object) -> KnowledgeConfigSnapshot:
    knowledge_bases: list[dict[str, object]] = []
    for source_type, block in knowledge_base.items():
        connectors = block.get("connectors", [])  # type: ignore[union-attr]
        for item in connectors:  # type: ignore[union-attr]
            source = dict(item)
            source["id"] = source.pop("connector_id")
            source["type"] = source_type
            tenant_id = str(source.pop("tenant_id"))
            kb_id = str(source.pop("kb_id"))
            knowledge_bases.append(
                {
                    "id": kb_id,
                    "tenant_id": tenant_id,
                    "sources": [source],
                }
            )
    return KnowledgeConfigSnapshot.model_validate({"knowledge_bases": knowledge_bases})


def test_google_drive_connectors_load_from_settings():
    from fleetent.knowledge_base import list_configured_connectors

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "enabled": True,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "recursive": True,
                    "credential_ref": "file:///secure/google.json",
                }
            ]
        }
    )

    connectors = list_configured_connectors(settings=settings)

    assert [
        (item.connector_id, item.connector_type, item.tenant_id, item.kb_id) for item in connectors
    ] == [("eng-drive", "google_drive", "default", "engineering")]
    assert connectors[0].enabled is True
    assert connectors[0].scope == "folder:folder-1"
    assert "google.json" in connectors[0].credential_ref_summary
    assert "/secure/" not in connectors[0].credential_ref_summary


def test_google_drive_connectors_load_explicit_env_fields_from_settings():
    from fleetent.knowledge_base import (
        get_connector_config,
        list_configured_connectors,
    )

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "enabled": True,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "recursive": True,
                    "access_token_env": "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
                    "refresh_token_env": "FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN",
                    "client_id_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_ID",
                    "client_secret_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
                }
            ]
        }
    )

    connectors = list_configured_connectors(settings=settings)
    definition = get_connector_config("eng-drive", settings=settings)

    assert connectors[0].credential_ref_summary == "env:FLEETENT_GOOGLE_DRIVE_*"
    assert definition.config.access_token_env == "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN"
    assert definition.config.client_secret_env == "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET"
    assert definition.config.token_uri_env == ""


def test_connectors_load_from_platform_yaml_knowledge_section(tmp_path, monkeypatch):
    from fleetent.knowledge_base import list_configured_connectors

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    (tmp_path / "platform.yaml").write_text(
        """
knowledge:
  knowledge_bases:
    - id: engineering
      tenant_id: default
      sources:
        - id: eng-drive
          type: google_drive
          folder_id: folder-1
          credential_ref: file:///secure/google.json
""",
        encoding="utf-8",
    )

    connectors = list_configured_connectors()

    assert [(item.connector_id, item.tenant_id, item.kb_id) for item in connectors] == [
        ("eng-drive", "default", "engineering")
    ]


def test_confluence_connectors_load_from_settings():
    from fleetent.knowledge_base import list_configured_connectors

    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "enabled": True,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username": "bot@example.com",
                    "space_key": "ENG",
                    "include_children": False,
                    "credential_ref": "env:FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    connectors = list_configured_connectors(settings=settings)

    assert connectors[0].connector_id == "eng-confluence"
    assert connectors[0].connector_type == "confluence"
    assert connectors[0].scope == "space:ENG"
    assert connectors[0].credential_ref_summary == "env:FLEETENT_CONFLUENCE_TOKEN"


def test_confluence_connectors_load_api_token_env_from_settings():
    from fleetent.knowledge_base import (
        get_connector_config,
        list_configured_connectors,
    )

    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "enabled": True,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                    "space_key": "ENG",
                    "include_children": False,
                    "api_token_env": "FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    connectors = list_configured_connectors(settings=settings)
    definition = get_connector_config("eng-confluence", settings=settings)

    assert connectors[0].credential_ref_summary == "env:FLEETENT_CONFLUENCE_TOKEN"
    assert definition.config.username == ""
    assert definition.config.username_env == "FLEETENT_CONFLUENCE_USERNAME"
    assert definition.config.api_token_env == "FLEETENT_CONFLUENCE_TOKEN"


def test_confluence_page_id_accepts_yaml_numeric_value():
    from fleetent.knowledge_base import get_connector_config

    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "enabled": True,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                    "scope_type": "page",
                    "page_id": 334954695,
                    "api_token_env": "FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    definition = get_connector_config("eng-confluence", settings=settings)

    assert definition.config.page_id == "334954695"


async def test_confluence_connector_username_can_load_from_env(monkeypatch):
    from fleetent.knowledge_base import operations, run_connector_sync
    from fleetent.knowledge_base.connectors.confluence import FakeConfluenceClient

    monkeypatch.setenv("FLEETENT_CONFLUENCE_USERNAME", "bot@example.com")
    monkeypatch.setenv("FLEETENT_CONFLUENCE_TOKEN", "test-token")
    monkeypatch.setattr(operations, "record_connector_status", lambda **kwargs: None)
    calls: list[tuple[str, str, str]] = []

    def fake_factory(base_url: str, username: str, credential_ref: str):
        calls.append((base_url, username, credential_ref))
        return FakeConfluenceClient(space_pages={"ENG": []})

    monkeypatch.setattr(operations, "_create_confluence_client", fake_factory)
    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                    "space_key": "ENG",
                    "credential_ref": "env:FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    result = await run_connector_sync("eng-confluence", settings=settings, dry_run=True)

    assert result.status == "dry_run_ok"
    assert calls == [
        (
            "https://example.atlassian.net/wiki",
            "bot@example.com",
            "FLEETENT_CONFLUENCE_TOKEN",
        )
    ]


def test_duplicate_connector_ids_fail_fast():
    with pytest.raises(ValueError, match="duplicate source id: same"):
        _settings(
            google_drive={
                "connectors": [
                    {
                        "connector_id": "same",
                        "tenant_id": "default",
                        "kb_id": "kb-a",
                        "folder_id": "folder-1",
                        "credential_ref": "file:///secure/google.json",
                    }
                ]
            },
            confluence={
                "connectors": [
                    {
                        "connector_id": "same",
                        "tenant_id": "default",
                        "kb_id": "kb-b",
                        "base_url": "https://example.atlassian.net/wiki",
                        "username": "bot@example.com",
                        "space_key": "ENG",
                        "credential_ref": "env:FLEETENT_CONFLUENCE_TOKEN",
                    }
                ]
            },
        )


def test_missing_required_connector_field_mentions_field_name():
    with pytest.raises(Exception, match="folder_id"):
        KnowledgeConfigSnapshot.model_validate(
            {
                "knowledge_bases": [
                    {
                        "id": "engineering",
                        "tenant_id": "default",
                        "sources": [
                            {
                                "id": "broken",
                                "type": "google_drive",
                                "credential_ref": "file:///secure/google.json",
                            }
                        ],
                    }
                ]
            }
        )


async def test_disabled_connector_is_listed_but_not_synced(monkeypatch):
    from fleetent.knowledge_base import (
        list_configured_connectors,
        operations,
        run_connector_sync,
    )

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "disabled-drive",
                    "enabled": False,
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": "file:///secure/google.json",
                }
            ]
        }
    )

    assert list_configured_connectors(settings=settings)[0].enabled is False
    monkeypatch.setattr(operations, "record_connector_status", lambda **kwargs: None)
    result = await run_connector_sync("disabled-drive", settings=settings)

    assert result.status == "disabled"
    assert result.summary == {}


async def test_missing_file_credential_is_reported(tmp_path):
    from fleetent.knowledge_base import check_connector

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": str(tmp_path / "missing.json"),
                }
            ]
        }
    )

    result = await check_connector("eng-drive", settings=settings)

    assert result.status == "credential_missing"
    assert "missing" in result.message.lower()


async def test_missing_env_credential_is_reported(monkeypatch):
    from fleetent.knowledge_base import check_connector

    monkeypatch.delenv("FLEETENT_CONFLUENCE_TOKEN", raising=False)
    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username": "bot@example.com",
                    "space_key": "ENG",
                    "credential_ref": "env:FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    result = await check_connector("eng-confluence", settings=settings)

    assert result.status == "credential_missing"


async def test_invalid_google_credential_payload_is_reported(tmp_path):
    from fleetent.knowledge_base import check_connector

    credential = tmp_path / "google.json"
    credential.write_text("not-json")
    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": str(credential),
                }
            ]
        }
    )

    result = await check_connector("eng-drive", settings=settings)

    assert result.status == "credential_invalid"


@dataclass
class _AuthFailDriveClient:
    def list_files(self, folder_id: str, *, recursive: bool) -> list[object]:
        from fleetent.knowledge_base.connectors.google_drive import (
            GoogleDriveAuthError,
        )

        raise GoogleDriveAuthError("token secret-123 failed")


async def test_fake_client_auth_failure_is_sanitized(tmp_path):
    from fleetent.knowledge_base import check_connector

    credential = tmp_path / "google.json"
    credential.write_text("{}")
    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": str(credential),
                }
            ]
        }
    )

    result = await check_connector(
        "eng-drive",
        settings=settings,
        google_drive_client=_AuthFailDriveClient(),
    )

    assert result.status == "auth_failed"
    assert "secret-123" not in result.message


@dataclass
class _ScopeFailDriveClient:
    def list_files(self, folder_id: str, *, recursive: bool) -> list[object]:
        raise RuntimeError("folder unreachable")


async def test_remote_scope_unreachable_is_reported(tmp_path):
    from fleetent.knowledge_base import check_connector

    credential = tmp_path / "google.json"
    credential.write_text("{}")
    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": str(credential),
                }
            ]
        }
    )

    result = await check_connector(
        "eng-drive",
        settings=settings,
        google_drive_client=_ScopeFailDriveClient(),
    )

    assert result.status == "scope_unreachable"


async def test_check_connector_uses_real_google_client_factory_by_default(tmp_path, monkeypatch):
    from fleetent.knowledge_base import check_connector, operations
    from fleetent.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

    credential = tmp_path / "google.json"
    credential.write_text('{"access_token":"test-token"}')
    calls: list[str] = []

    def fake_factory(config):
        calls.append(config.credential_ref)
        return FakeGoogleDriveClient(files_by_folder={"folder-1": []})

    monkeypatch.setattr(operations, "_create_google_drive_client", fake_factory)
    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": str(credential),
                }
            ]
        }
    )

    result = await check_connector("eng-drive", settings=settings)

    assert result.status == "ok"
    assert calls == [str(credential)]


async def test_sync_uses_real_confluence_client_factory_by_default(monkeypatch):
    from fleetent.knowledge_base import operations, run_connector_sync
    from fleetent.knowledge_base.connectors.confluence import (
        ConfluencePage,
        FakeConfluenceClient,
    )

    monkeypatch.setenv("FLEETENT_CONFLUENCE_TOKEN", "test-token")
    monkeypatch.setattr(operations, "record_connector_status", lambda **kwargs: None)
    calls: list[tuple[str, str, str]] = []

    def fake_factory(base_url: str, username: str, credential_ref: str):
        calls.append((base_url, username, credential_ref))
        return FakeConfluenceClient(
            space_pages={
                "ENG": [
                    [
                        ConfluencePage(
                            id="page-1",
                            title="Runbook",
                            space_key="ENG",
                            storage_html="<h1>Runbook</h1>",
                            version=1,
                            modified_time="2026-06-02T00:00:00Z",
                        )
                    ]
                ]
            }
        )

    monkeypatch.setattr(operations, "_create_confluence_client", fake_factory)
    settings = _settings(
        confluence={
            "connectors": [
                {
                    "connector_id": "eng-confluence",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "base_url": "https://example.atlassian.net/wiki",
                    "username": "bot@example.com",
                    "space_key": "ENG",
                    "credential_ref": "env:FLEETENT_CONFLUENCE_TOKEN",
                }
            ]
        }
    )

    result = await run_connector_sync("eng-confluence", settings=settings, dry_run=True)

    assert result.status == "dry_run_ok"
    assert result.summary["scanned"] == 1
    assert result.summary["planned"] == 1
    assert calls == [
        (
            "https://example.atlassian.net/wiki",
            "bot@example.com",
            "FLEETENT_CONFLUENCE_TOKEN",
        )
    ]


# Removed test_connector_settings_example_contains_only_env_secret_references:
# legacy settings.yaml examples were dropped; KB connector secret-reference validation
# lives with Platform knowledge config.
