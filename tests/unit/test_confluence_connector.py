from __future__ import annotations

import httpx
import pytest
import respx


def test_confluence_connector_config_public_api_is_importable():
    from fleetent.knowledge_base import ConfluenceConnectorConfig

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
    from fleetent.knowledge_base import ConfluenceConnectorConfig

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
    from fleetent.knowledge_base.connectors.confluence import (
        CredentialRefResolver,
    )

    monkeypatch.setenv("CONFLUENCE_TOKEN", "env-token")
    token_path = tmp_path / "token.txt"
    token_path.write_text("file-token", encoding="utf-8")
    resolver = CredentialRefResolver()

    assert resolver.resolve("env:CONFLUENCE_TOKEN").payload == "env-token"
    assert resolver.resolve(str(token_path)).payload == "file-token"


@respx.mock
def test_http_confluence_client_lists_space_pages_with_pagination(monkeypatch):
    from fleetent.knowledge_base.connectors.confluence import HttpConfluenceClient

    monkeypatch.setenv("CONFLUENCE_TOKEN", "conf-token")
    first = respx.get("https://example.atlassian.net/wiki/rest/api/content").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [_confluence_page_json("1", "Runbook")],
                    "_links": {"next": "/rest/api/content?start=1"},
                },
            ),
            httpx.Response(200, json={"results": [_confluence_page_json("2", "Deploy")]}),
        ]
    )

    pages = HttpConfluenceClient(
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
    ).list_space_pages("ENG")

    assert [[page.id for page in group] for group in pages] == [["1"], ["2"]]
    request = first.calls[0].request
    assert request.url.params["spaceKey"] == "ENG"
    assert (
        request.url.params["expand"] == "body.storage,version,space,ancestors,history.lastUpdated"
    )
    assert request.headers["Authorization"].startswith("Basic ")


@respx.mock
def test_http_confluence_client_gets_page_and_children(monkeypatch):
    from fleetent.knowledge_base.connectors.confluence import HttpConfluenceClient

    monkeypatch.setenv("CONFLUENCE_TOKEN", "conf-token")
    page_route = respx.get("https://example.atlassian.net/wiki/rest/api/content/root").mock(
        return_value=httpx.Response(200, json=_confluence_page_json("root", "Root"))
    )
    child_route = respx.get(
        "https://example.atlassian.net/wiki/rest/api/content/root/child/page"
    ).mock(
        return_value=httpx.Response(200, json={"results": [_confluence_page_json("c1", "Child")]})
    )
    client = HttpConfluenceClient(
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
    )

    page = client.get_page("root")
    children = client.list_child_pages("root")

    assert page.id == "root"
    assert page.title == "Root"
    assert [child.id for child in children] == ["c1"]
    assert page_route.calls.last.request.url.params["expand"]
    assert child_route.calls.last.request.url.params["expand"]


@respx.mock
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, "ConfluenceAuthError"),
        (403, "ConfluenceAuthError"),
        (429, "ConfluenceRateLimitError"),
    ],
)
def test_http_confluence_client_maps_http_errors(monkeypatch, status_code, expected_error):
    from fleetent.knowledge_base.connectors import confluence
    from fleetent.knowledge_base.connectors.confluence import HttpConfluenceClient

    monkeypatch.setenv("CONFLUENCE_TOKEN", "conf-token")
    respx.get("https://example.atlassian.net/wiki/rest/api/content").mock(
        return_value=httpx.Response(status_code, headers={"Retry-After": "2"})
    )
    client = HttpConfluenceClient(
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
    )

    with pytest.raises(getattr(confluence, expected_error)):
        client.list_space_pages("ENG")


async def test_confluence_auth_failure_marks_summary_auth_failed():
    from fleetent.knowledge_base.connectors.confluence import (
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
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors.confluence import (
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
    from fleetent.knowledge_base.connectors.confluence import (
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


async def test_confluence_malformed_page_metadata_is_counted_as_failed():
    from fleetent.knowledge_base.connectors.confluence import (
        ConfluencePage,
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    plan = await plan_confluence_sync(
        _space_config(),
        client=FakeConfluenceClient(
            space_pages={
                "ENG": [
                    [
                        ConfluencePage(
                            id="bad-page",
                            title="Bad metadata",
                            space_key="ENG",
                            storage_html="<p>Body</p>",
                            version=1,
                            modified_time="not-a-timestamp",
                        )
                    ]
                ]
            }
        ),
    )

    assert plan.items == []
    assert plan.summary.scanned == 1
    assert plan.summary.failed == 1


async def test_confluence_archive_missing_failure_is_counted_per_item(monkeypatch):
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors.confluence import (
        ConfluenceSyncPlan,
        FakeConfluenceClient,
        execute_confluence_sync_plan,
    )
    from fleetent.knowledge_base.sync_planner import SyncPlanItem, SyncPlanSummary

    async def fail_archive(document_id: str) -> None:
        raise RuntimeError(f"cannot archive {document_id}")

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime, "archive", fail_archive)
    plan = ConfluenceSyncPlan(
        config=_space_config(),
        items=[
            SyncPlanItem(
                action=SyncAction.ARCHIVE_MISSING,
                source_id="conf-eng",
                tenant_id="tenant-a",
                kb_id="engineering",
                source_path="confluence://missing",
                filename="missing",
                document_format="html",
                mtime_ns=1,
                content_hash="old",
                document_id="kb-doc-1",
            )
        ],
        pages={},
        summary=SyncPlanSummary(scanned=0, planned=1, archived=1),
    )

    summary = await execute_confluence_sync_plan(plan, client=FakeConfluenceClient())

    assert summary.archived == 0
    assert summary.failed == 1


def test_parse_confluence_page_uses_storage_html_and_metadata():
    from fleetent.knowledge_base.connectors.confluence import (
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
    from fleetent.knowledge_base.connectors.confluence import (
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
    from fleetent.knowledge_base.connectors.confluence import (
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
    from fleetent.knowledge_base import ConfluenceConnectorConfig

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
    from fleetent.knowledge_base import ConfluenceConnectorConfig

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
    from fleetent.knowledge_base.connectors.confluence import ConfluencePage

    return ConfluencePage(
        id=page_id,
        title=title,
        space_key="ENG",
        storage_html=f"<h1>{title}</h1><p>Body</p>",
        version=1,
        modified_time="2026-06-02T00:00:00+00:00",
        ancestors=["Engineering"],
    )


def _confluence_page_json(page_id: str, title: str):
    return {
        "id": page_id,
        "title": title,
        "space": {"key": "ENG"},
        "body": {"storage": {"value": f"<h1>{title}</h1><p>Body</p>"}},
        "version": {"number": 2, "when": "2026-06-02T00:00:00.000Z"},
        "history": {"lastUpdated": {"when": "2026-06-02T00:00:00.000Z"}},
        "ancestors": [{"title": "Engineering"}],
    }


async def _noop_sleep(seconds: float) -> None:
    return None
