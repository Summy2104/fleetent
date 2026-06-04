from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from fleetent.config import Settings


def _settings(**knowledge_base: object) -> Settings:
    return Settings(anthropic_api_key="test-key", knowledge_base=knowledge_base)


def test_google_drive_connectors_load_from_settings():
    from fleetent.intelligence.knowledge_base import list_configured_connectors

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
    from fleetent.intelligence.knowledge_base import (
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


def test_confluence_connectors_load_from_settings():
    from fleetent.intelligence.knowledge_base import list_configured_connectors

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
    from fleetent.intelligence.knowledge_base import (
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
    from fleetent.intelligence.knowledge_base import get_connector_config

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
    from fleetent.intelligence.knowledge_base import operations, run_connector_sync
    from fleetent.intelligence.knowledge_base.connectors.confluence import FakeConfluenceClient

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
    from fleetent.intelligence.knowledge_base import list_configured_connectors

    settings = _settings(
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

    with pytest.raises(ValueError, match="duplicate connector_id: same"):
        list_configured_connectors(settings=settings)


def test_missing_required_connector_field_mentions_field_name(tmp_path, monkeypatch):
    import fleetent.config as cfg

    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        "\n".join(
            [
                "knowledge_base:",
                "  google_drive:",
                "    connectors:",
                "      - connector_id: broken",
                "        tenant_id: default",
                "        kb_id: engineering",
                "        credential_ref: file:///secure/google.json",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)

    with pytest.raises(Exception, match="folder_id"):
        Settings(anthropic_api_key="test-key")


async def test_disabled_connector_is_listed_but_not_synced(monkeypatch):
    from fleetent.intelligence.knowledge_base import (
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
    from fleetent.intelligence.knowledge_base import check_connector

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
    from fleetent.intelligence.knowledge_base import check_connector

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
    from fleetent.intelligence.knowledge_base import check_connector

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
        from fleetent.intelligence.knowledge_base.connectors.google_drive import (
            GoogleDriveAuthError,
        )

        raise GoogleDriveAuthError("token secret-123 failed")


async def test_fake_client_auth_failure_is_sanitized(tmp_path):
    from fleetent.intelligence.knowledge_base import check_connector

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
    from fleetent.intelligence.knowledge_base import check_connector

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
    from fleetent.intelligence.knowledge_base import check_connector, operations
    from fleetent.intelligence.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

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
    from fleetent.intelligence.knowledge_base import operations, run_connector_sync
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
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


def test_connector_settings_example_contains_only_env_secret_references():
    example = Path("config/settings.yaml.example").read_text()

    assert "connectors:" in example
    assert "access_token_env:" in example
    assert "api_token_env:" in example
    assert "refresh_token:" not in example
    assert "client_secret:" not in example
    assert "api_token:" not in example
