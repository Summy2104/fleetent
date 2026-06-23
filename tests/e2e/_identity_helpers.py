from __future__ import annotations

import base64
import contextlib
import os
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from fleetent.platform.user_management.oidc import OidcRelyingParty, OidcSettings
from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    running_process,
    wait_for_condition,
    wait_for_http_ready,
)
from tests.e2e.conftest import (
    ManagedStack,
    _admin_session_headers,
    _agent_status,
    _register_node,
    _seed_managed_agent,
)
from tests.integration._migration_template import apply_migrations


@dataclass
class OidcStubHandle:
    issuer: str
    client_id: str
    client_secret: str
    client_secret_env: str
    email: str
    client: httpx.Client

    def relying_party(self, settings: OidcSettings) -> OidcRelyingParty:
        return OidcRelyingParty(settings, http_client=self.client)


@dataclass(frozen=True)
class ManagedIdentityStack:
    platform_url: str
    node_id: str
    node_service_key: str
    agent_id: int
    agent_name: str
    agent_status: dict[str, object]
    admin_session_headers: dict[str, str]
    desired_state_cache_path: Path
    home_dir: Path
    db_path: Path


@dataclass(frozen=True)
class OidcLoginResult:
    callback: httpx.Response
    token: str


def build_oidc_settings(
    stub: OidcStubHandle,
    *,
    redirect_uri: str = "https://fleetent.example.com/admin/oidc/callback",
    tenant: str = "default",
) -> OidcSettings:
    return OidcSettings(
        enabled=True,
        issuer=stub.issuer,
        client_id=stub.client_id,
        client_secret_env=stub.client_secret_env,
        redirect_uri=redirect_uri,
        tenant=tenant,
    )


@contextlib.contextmanager
def start_oidc_stub(
    *,
    email: str,
    client_id: str = "fleetent-web",
    client_secret: str = "oidc-secret",
    client_secret_env: str = "FLEETENT_OIDC_CLIENT_SECRET",
) -> Iterator[OidcStubHandle]:
    port = reserve_port()
    issuer = f"http://127.0.0.1:{port}"
    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.e2e._oidc_stub:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    env = child_env(
        extra={
            "OIDC_STUB_ISSUER": issuer,
            "OIDC_STUB_CLIENT_ID": client_id,
            "OIDC_STUB_CLIENT_SECRET": client_secret,
            "OIDC_STUB_CLIENT_SECRET_ENV": client_secret_env,
            "OIDC_STUB_EMAIL": email,
        }
    )
    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_http_ready(proc, f"{issuer}/health", timeout=10.0)
        client = httpx.Client(follow_redirects=False, timeout=10.0)
        original_secret = os.environ.get(client_secret_env)
        os.environ[client_secret_env] = client_secret
        try:
            yield OidcStubHandle(
                issuer=issuer,
                client_id=client_id,
                client_secret=client_secret,
                client_secret_env=client_secret_env,
                email=email,
                client=client,
            )
        finally:
            client.close()
            if original_secret is None:
                os.environ.pop(client_secret_env, None)
            else:
                os.environ[client_secret_env] = original_secret


@contextlib.contextmanager
def start_managed_identity_stack(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_stub_base_url: str,
    oidc_stub: OidcStubHandle | None = None,
    tenant: str = "default",
) -> Iterator[ManagedIdentityStack]:
    home_dir = tmp_path / "fleetent-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)

    secret_key = base64.urlsafe_b64encode(b"9" * 32).decode("ascii")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))
    monkeypatch.setenv("FLEETENT_SECRET_KEY", secret_key)

    node_id = "node-e2e"
    common_env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(home_dir),
            "FLEETENT_SECRET_KEY": secret_key,
            "FLEETENT_FORWARDER_HOST_OVERRIDE": "127.0.0.1",
        }
    )
    if oidc_stub is not None:
        common_env.update(
            {
                "OIDC__ENABLED": "true",
                "OIDC__ISSUER": oidc_stub.issuer,
                "OIDC__CLIENT_ID": oidc_stub.client_id,
                "OIDC__CLIENT_SECRET_ENV": oidc_stub.client_secret_env,
                "OIDC__TENANT": tenant,
                oidc_stub.client_secret_env: oidc_stub.client_secret,
            }
        )

    node_service_key = _register_node(env=common_env, node_id=node_id)
    agent_id, agent_name = _seed_managed_agent(llm_stub_base_url=llm_stub_base_url, node_id=node_id)
    platform_port = reserve_port()
    platform_url = f"http://127.0.0.1:{platform_port}"
    if oidc_stub is not None:
        common_env["OIDC__REDIRECT_URI"] = f"{platform_url}/admin/oidc/callback"

    platform_argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "fleetent.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(platform_port),
        "--log-level",
        "warning",
    ]
    node_env = {
        **common_env,
        "FLEETENT_NODE_PLATFORM_URL": platform_url,
        "FLEETENT_NODE_ID": node_id,
        "FLEETENT_NODE_SERVICE_KEY": node_service_key,
        "FLEETENT_NODE_INTERVAL_SECONDS": "1",
    }
    node_argv = [sys.executable, "-m", "fleetent", "node", "start"]

    with contextlib.ExitStack() as stack:
        platform_proc = stack.enter_context(
            running_process(platform_argv, env=common_env, cwd=repo_root())
        )
        wait_for_http_ready(platform_proc, f"{platform_url}/health", timeout=20.0)
        stack.enter_context(running_process(node_argv, env=node_env, cwd=repo_root()))
        status = wait_for_condition(
            lambda: _agent_status(agent_id=agent_id, node_id=node_id),
            timeout=30.0,
            interval=0.5,
            description="managed agent healthy status",
        )
        yield ManagedIdentityStack(
            platform_url=platform_url,
            node_id=node_id,
            node_service_key=node_service_key,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_status=status,
            admin_session_headers=_admin_session_headers(platform_url),
            desired_state_cache_path=home_dir / "node" / "desired-state-cache.json",
            home_dir=home_dir,
            db_path=db_path,
        )


def extract_session_token(location: str) -> str:
    return parse_qs(urlparse(location).query)["token"][0]


def login_via_oidc(*, platform_url: str, client: httpx.Client | None = None) -> OidcLoginResult:
    owned_client = client is None
    http = client or httpx.Client(follow_redirects=False, timeout=10.0)
    try:
        login = http.get(f"{platform_url}/admin/oidc/login")
        authorize = http.get(login.headers["location"])
        callback = http.get(authorize.headers["location"])
        return OidcLoginResult(
            callback=callback,
            token=extract_session_token(callback.headers["location"]),
        )
    finally:
        if owned_client:
            http.close()


def count_users_with_email(tenant_id: str, email: str) -> int:
    normalized_email = email.strip().lower()
    db_url = os.environ["DATABASE_URL"]
    db_path = db_url.removeprefix("sqlite:///")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE tenant_id = :tenant_id AND lower(trim(email)) = :email
            """,
            {"tenant_id": tenant_id, "email": normalized_email},
        ).fetchone()
    assert row is not None
    return int(row[0])


def confirm_link_code(
    *,
    platform_url: str,
    node_id: str,
    node_service_key: str,
    platform: str,
    platform_user_id: str,
    code: str,
) -> httpx.Response:
    return httpx.post(
        f"{platform_url}/nodes/{node_id}/link-confirm",
        headers={"Authorization": f"Bearer {node_service_key}"},
        json={
            "platform": platform,
            "platform_user_id": platform_user_id,
            "code": code,
        },
        timeout=10.0,
    )


def managed_stack_view(stack: ManagedIdentityStack) -> ManagedStack:
    return ManagedStack(
        platform_url=stack.platform_url,
        node_id=stack.node_id,
        agent_id=stack.agent_id,
        agent_name=stack.agent_name,
        agent_status=stack.agent_status,
        admin_session_headers=stack.admin_session_headers,
        desired_state_cache_path=stack.desired_state_cache_path,
        home_dir=stack.home_dir,
        db_path=stack.db_path,
    )
