from __future__ import annotations

import pytest


def test_confluence_connector_config_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import ConfluenceConnectorConfig

    config = ConfluenceConnectorConfig(
        connector_id="conf-eng",
        tenant_id="tenant-a",
        kb_id="engineering",
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
        scope_type="space",
        space_key="ENG",
    )

    assert config.connector_id == "conf-eng"
    assert config.tenant_id == "tenant-a"
    assert config.kb_id == "engineering"
    assert config.base_url == "https://example.atlassian.net/wiki"
    assert config.username == "bot@example.com"
    assert config.credential_ref == "env:CONFLUENCE_TOKEN"
    assert config.scope_type == "space"
    assert config.space_key == "ENG"


def test_confluence_config_supports_page_scope_with_children():
    from fleetent.intelligence.knowledge_base import ConfluenceConnectorConfig

    config = ConfluenceConnectorConfig(
        connector_id="conf-page",
        tenant_id="tenant-a",
        kb_id="engineering",
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="file:///secure/confluence-token",
        scope_type="page",
        page_id="123",
        include_children=True,
    )

    assert config.page_id == "123"
    assert config.include_children is True


def test_confluence_credential_ref_resolver_supports_env_and_file(tmp_path, monkeypatch):
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        CredentialRefResolver,
    )

    monkeypatch.setenv("CONFLUENCE_TOKEN", "env-token")
    token_path = tmp_path / "token.txt"
    token_path.write_text("file-token", encoding="utf-8")
    resolver = CredentialRefResolver()

    assert resolver.resolve("env:CONFLUENCE_TOKEN").payload == "env-token"
    assert resolver.resolve(str(token_path)).payload == "file-token"


async def test_confluence_auth_failure_marks_summary_auth_failed():
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    plan = await plan_confluence_sync(
        _space_config(),
        client=FakeConfluenceClient(auth_failed=True),
    )

    assert plan.items == []
    assert plan.summary.auth_failed == 1
    assert plan.summary.failed == 1


async def test_confluence_space_scope_lists_pages_with_pagination():
    from fleetent.intelligence.knowledge_base import SyncAction
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    client = FakeConfluenceClient(
        space_pages={
            "ENG": [
                [_page("1", "Runbook")],
                [_page("2", "Deploy")],
            ]
        }
    )

    plan = await plan_confluence_sync(_space_config(), client=client)

    assert [item.source_path for item in plan.items] == ["confluence://1", "confluence://2"]
    assert [item.action for item in plan.items] == [
        SyncAction.INGEST_NEW,
        SyncAction.INGEST_NEW,
    ]


async def test_confluence_page_scope_lists_page_and_optional_descendants():
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    config = _page_config(include_children=True)
    client = FakeConfluenceClient(
        pages_by_id={"root": _page("root", "Root")},
        child_pages={"root": [_page("child", "Child")]},
    )

    plan = await plan_confluence_sync(config, client=client)

    assert [item.source_path for item in plan.items] == [
        "confluence://root",
        "confluence://child",
    ]


def test_parse_confluence_page_uses_storage_html_and_metadata():
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        ConfluencePage,
        parse_confluence_page,
    )

    parsed = parse_confluence_page(
        ConfluencePage(
            id="1",
            title="Runbook",
            space_key="ENG",
            storage_html="<h1>Runbook</h1><p>Restart service</p>",
            version=3,
            modified_time="2026-06-02T00:00:00+00:00",
            ancestors=["Engineering", "Ops"],
        )
    )

    assert parsed.format == "html"
    assert parsed.filename == "Runbook.html"
    assert parsed.metadata["space_key"] == "ENG"
    assert parsed.metadata["page_id"] == "1"
    assert parsed.metadata["ancestor_path"] == "Engineering > Ops"


async def test_confluence_retry_after_retries_once(monkeypatch):
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        ConfluenceRateLimitError,
        FakeConfluenceClient,
        list_confluence_scope_pages,
    )

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = FakeConfluenceClient(
        space_pages={"ENG": [[_page("1", "Runbook")]]},
        transient_errors=[ConfluenceRateLimitError(retry_after_seconds=0.1)],
    )

    pages = await list_confluence_scope_pages(
        _space_config(requests_per_minute=600),
        client=client,
        sleep=fake_sleep,
    )

    assert [page.id for page in pages] == ["1"]
    assert sleeps == [0.1]


async def test_confluence_retry_limit_returns_failure():
    from fleetent.intelligence.knowledge_base.connectors.confluence import (
        ConfluenceRateLimitError,
        FakeConfluenceClient,
        list_confluence_scope_pages,
    )

    client = FakeConfluenceClient(
        transient_errors=[
            ConfluenceRateLimitError(retry_after_seconds=0),
            ConfluenceRateLimitError(retry_after_seconds=0),
        ]
    )

    with pytest.raises(ConfluenceRateLimitError):
        await list_confluence_scope_pages(
            _space_config(max_retries=1),
            client=client,
            sleep=_noop_sleep,
        )


def _space_config(**overrides):
    from fleetent.intelligence.knowledge_base import ConfluenceConnectorConfig

    values = {
        "connector_id": "conf-eng",
        "tenant_id": "tenant-a",
        "kb_id": "engineering",
        "base_url": "https://example.atlassian.net/wiki",
        "username": "bot@example.com",
        "credential_ref": "env:CONFLUENCE_TOKEN",
        "scope_type": "space",
        "space_key": "ENG",
    }
    values.update(overrides)
    return ConfluenceConnectorConfig(**values)


def _page_config(*, include_children: bool):
    from fleetent.intelligence.knowledge_base import ConfluenceConnectorConfig

    return ConfluenceConnectorConfig(
        connector_id="conf-page",
        tenant_id="tenant-a",
        kb_id="engineering",
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
        scope_type="page",
        page_id="root",
        include_children=include_children,
    )


def _page(page_id: str, title: str):
    from fleetent.intelligence.knowledge_base.connectors.confluence import ConfluencePage

    return ConfluencePage(
        id=page_id,
        title=title,
        space_key="ENG",
        storage_html=f"<h1>{title}</h1><p>Body</p>",
        version=1,
        modified_time="2026-06-02T00:00:00+00:00",
        ancestors=["Engineering"],
    )


async def _noop_sleep(seconds: float) -> None:
    return None
