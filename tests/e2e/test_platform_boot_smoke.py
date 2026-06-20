from __future__ import annotations

import sys

import httpx

from tests.e2e._entrypoint_smoke import child_env, repo_root, reserve_port, running_process, wait_for_http_ready
from tests.integration._migration_template import apply_migrations


def test_platform_uvicorn_boots_and_serves_health(tmp_path) -> None:
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    port = reserve_port()
    env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(tmp_path / "home"),
        }
    )
    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "fleetent.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]

    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_http_ready(proc, f"http://127.0.0.1:{port}/health")
        response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
