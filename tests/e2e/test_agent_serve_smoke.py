from __future__ import annotations

import sys
from pathlib import Path

import httpx
import yaml

from fleetent import agent_config
from tests.e2e._entrypoint_smoke import child_env, repo_root, reserve_port, running_process, wait_for_http_ready


def _write_agent_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "smoke-agent",
                "version": 1,
                "system_prompt": "You are the smoke test agent.",
                "models": agent_config.default_models().model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )


def test_agent_run_serves_health(tmp_path) -> None:
    home = tmp_path / "smoke-agent"
    _write_agent_home(home)
    port = reserve_port()
    env = child_env(extra={"FLEETENT_HOME": str(tmp_path / "fleetent-home")})
    argv = [
        sys.executable,
        "-m",
        "fleetent",
        "agent",
        "run",
        "smoke-agent",
        "--home",
        str(home),
        "--port",
        str(port),
    ]

    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_http_ready(proc, f"http://127.0.0.1:{port}/health")
        response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "agent": "smoke-agent"}
