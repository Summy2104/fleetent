from __future__ import annotations

import base64
import hashlib
import json

import httpx
import respx
import yaml

from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredSkill, DesiredSkillFile, DesiredState


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _status_route() -> respx.Route:
    return respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )


class FakeBackend:
    def __init__(
        self,
        alive: dict[str, int | None],
        gateway_ports: dict[str, int | None] | None = None,
    ) -> None:
        self.alive = alive
        self.gateway_ports = gateway_ports or {}
        self.spawn_calls: list[tuple[str, dict[str, str] | None]] = []
        self.stop_calls: list[str] = []

    def spawn(self, agent_name: str, env: dict[str, str] | None = None) -> None:
        self.spawn_calls.append((agent_name, env))

    def stop(self, agent_name: str) -> None:
        self.stop_calls.append(agent_name)

    def is_alive(self, agent_name: str) -> int | None:
        return self.alive.get(agent_name)

    def gateway_port(self, agent_name: str) -> int | None:
        return self.gateway_ports.get(agent_name)


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _desired(
    config: dict[str, object] | None = None,
    secrets: dict[str, str] | None = None,
    source: str = "remote",
) -> DesiredState:
    return DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config=config or {"name": "support"},
                secrets=secrets or {},
            )
        ],
        source=source,
    )


def _post_body(route: respx.Route) -> dict[str, object]:
    return json.loads(route.calls[0].request.content)


@respx.mock
def test_reconcile_spawns_missing_desired_agent_after_writing_home(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    backend = FakeBackend({"support": None})
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == [("support", {})]
    home = tmp_path / "agents" / "support"
    assert yaml.safe_load((home / "agent.yaml").read_text()) == {"name": "support"}
    assert route.called


@respx.mock
def test_reconcile_stops_running_agent_missing_from_desired(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(DesiredState(node_id="node-a", agents=[]))

    assert backend.stop_calls == ["support"]
    assert route.called


@respx.mock
def test_reconcile_readopts_live_agent_without_respawn(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == []
    assert backend.stop_calls == []
    assert route.calls[0].request.content


@respx.mock
def test_reconcile_respawns_crashed_agent(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == [("support", {})]
    assert route.called


@respx.mock
def test_reconcile_restarts_running_agent_when_config_hash_changes(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "old-hash"}',
        encoding="utf-8",
    )
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})
    desired = _desired({"name": "support", "system_prompt": "updated"})

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert backend.stop_calls == ["support"]
    assert backend.spawn_calls == [("support", {})]
    hashes = (state_dir / "applied-config-hashes.json").read_text(encoding="utf-8")
    assert (
        hashlib.sha256(
            yaml.safe_dump({"name": "support", "system_prompt": "updated"}, sort_keys=True).encode()
        ).hexdigest()
        in hashes
    )
    assert route.called


@respx.mock
def test_reconcile_keeps_running_agent_when_config_hash_matches(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    desired_config = {"name": "support", "system_prompt": "same"}
    desired_hash = hashlib.sha256(
        yaml.safe_dump(desired_config, sort_keys=True).encode()
    ).hexdigest()
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump(desired_config))
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "' + desired_hash + '"}',
        encoding="utf-8",
    )
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired(desired_config))

    assert backend.stop_calls == []
    assert backend.spawn_calls == []
    assert route.called


@respx.mock
def test_reconcile_status_post_failure_does_not_raise(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.post("https://platform.internal/nodes/node-a/status").mock(
        side_effect=httpx.ConnectError("boom")
    )
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == [("support", {})]


@respx.mock
def test_reconcile_reports_agent_health_from_loopback_probe_and_pid_fallback(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.get("http://127.0.0.1:9101/health").mock(return_value=httpx.Response(200))
    respx.get("http://127.0.0.1:9102/health").mock(return_value=httpx.Response(503))
    status_route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(agent_id=101, name="support", config={"name": "support"}, secrets={}),
            DesiredAgent(agent_id=102, name="billing", config={"name": "billing"}, secrets={}),
            DesiredAgent(agent_id=103, name="legacy", config={"name": "legacy"}, secrets={}),
        ],
    )
    backend = FakeBackend(
        {"support": 11111, "billing": 22222, "legacy": 33333},
        gateway_ports={"support": 9101, "billing": 9102},
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert _post_body(status_route) == {
        "agents": [
            {"agent_id": 101, "phase": "running", "pid": 11111, "health": "healthy"},
            {"agent_id": 102, "phase": "running", "pid": 22222, "health": "unhealthy"},
            {"agent_id": 103, "phase": "running", "pid": 33333, "health": "healthy"},
        ]
    }


@respx.mock
def test_reconcile_marks_probe_errors_unhealthy_without_interrupting_other_agents(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.get("http://127.0.0.1:9201/health").mock(side_effect=httpx.ConnectTimeout("boom"))
    respx.get("http://127.0.0.1:9202/health").mock(return_value=httpx.Response(200))
    status_route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(agent_id=101, name="support", config={"name": "support"}, secrets={}),
            DesiredAgent(agent_id=102, name="sales", config={"name": "sales"}, secrets={}),
        ],
    )
    backend = FakeBackend(
        {"support": 11111, "sales": 22222},
        gateway_ports={"support": 9201, "sales": 9202},
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert _post_body(status_route) == {
        "agents": [
            {"agent_id": 101, "phase": "running", "pid": 11111, "health": "unhealthy"},
            {"agent_id": 102, "phase": "running", "pid": 22222, "health": "healthy"},
        ]
    }


@respx.mock
def test_reconcile_passes_secrets_to_spawn_and_reuses_them_on_hash_restart(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": None})
    desired = _desired(secrets={"ANTHROPIC_API_KEY": "sk-live-secret"})

    reconciler = NodeReconciler(_config(tmp_path), backend)
    reconciler.reconcile(desired)

    backend.alive["support"] = 12345
    desired_updated = _desired(
        {"name": "support", "system_prompt": "updated"},
        secrets={"ANTHROPIC_API_KEY": "sk-live-secret"},
    )
    reconciler.reconcile(desired_updated)

    assert backend.stop_calls == ["support"]
    assert backend.spawn_calls == [
        ("support", {"ANTHROPIC_API_KEY": "sk-live-secret"}),
        ("support", {"ANTHROPIC_API_KEY": "sk-live-secret"}),
    ]
    assert route.called


@respx.mock
def test_reconcile_defers_cached_start_without_secrets_but_keeps_running_agent(
    tmp_path, monkeypatch
):
    from fleetent.node import reconcile as reconcile_module
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    warnings: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            warnings.append((message, fields))

    monkeypatch.setattr(reconcile_module, "_logger", FakeLogger())

    running_backend = FakeBackend({"support": 12345})
    NodeReconciler(_config(tmp_path), running_backend).reconcile(
        _desired(secrets={}, source="cache")
    )

    waiting_backend = FakeBackend({"support": None})
    NodeReconciler(_config(tmp_path), waiting_backend).reconcile(
        _desired(secrets={}, source="cache")
    )

    assert running_backend.stop_calls == []
    assert running_backend.spawn_calls == []
    assert waiting_backend.spawn_calls == []
    assert warnings == [
        (
            "node_secret_start_deferred",
            {"agent_name": "support", "secret_env_names": [], "secret_count": 0},
        )
    ]
    assert route.called


@respx.mock
def test_write_home_creates_env_with_tui_token(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    backend = FakeBackend({"support": None})
    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    env_path = tmp_path / "agents" / "support" / ".env"
    assert env_path.exists()
    lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert "FLEETENT_TUI_TOKEN" in lines
    token = lines["FLEETENT_TUI_TOKEN"]
    assert token.startswith("ma-")
    assert len(token) == 67


@respx.mock
def test_write_home_preserves_existing_env_token_on_config_restart(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    existing_token = "ma-" + "d" * 64
    (home / ".env").write_text(f"FLEETENT_TUI_TOKEN={existing_token}\n", encoding="utf-8")

    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "old-hash"}', encoding="utf-8"
    )

    backend = FakeBackend({"support": 12345})
    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired({"name": "support", "version": 2})
    )

    env_content = (home / ".env").read_text(encoding="utf-8")
    assert f"FLEETENT_TUI_TOKEN={existing_token}" in env_content


@respx.mock
def test_reconcile_logs_secret_metadata_without_plaintext_on_spawn(tmp_path, monkeypatch):
    from fleetent.node import reconcile as reconcile_module
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    records: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def info(self, message: str, **fields: object) -> None:
            records.append((message, fields))

        def warn(self, message: str, **fields: object) -> None:
            pass  # reconcile may warn on config parse errors; not under test here

    monkeypatch.setattr(reconcile_module, "_logger", FakeLogger())
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired(secrets={"ANTHROPIC_API_KEY": "sk-live-secret"})
    )

    assert records == [
        (
            "node_agent_spawn",
            {
                "agent_name": "support",
                "secret_env_names": ["ANTHROPIC_API_KEY"],
                "secret_count": 1,
            },
        )
    ]
    assert route.called


def _config_hash_of(config: dict[str, object]) -> str:
    return hashlib.sha256(yaml.safe_dump(config, sort_keys=True).encode()).hexdigest()


def _desired_with_skills(
    skills: list[DesiredSkill],
    *,
    config: dict[str, object] | None = None,
    secrets: dict[str, str] | None = None,
    source: str = "remote",
) -> DesiredState:
    return DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config=config or {"name": "support"},
                secrets=secrets or {},
                skills=skills,
            )
        ],
        source=source,
    )


@respx.mock
def test_reconcile_materializes_skill_files_and_writes_manifest(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    _status_route()
    backend = FakeBackend({"support": None})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[
            DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"---\nname: alpha\n---\nbody")),
            DesiredSkillFile(path="scripts/run.py", content_b64=_b64(b"print(1)\n")),
        ],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired_with_skills([skill]))

    skills_root = tmp_path / "agents" / "support" / "skills"
    assert (skills_root / "alpha" / "SKILL.md").read_bytes() == b"---\nname: alpha\n---\nbody"
    assert (skills_root / "alpha" / "scripts" / "run.py").read_bytes() == b"print(1)\n"
    manifest = json.loads((tmp_path / "agents" / "support" / ".node-skills.json").read_text())
    assert manifest == {"alpha": "v1"}
    assert backend.spawn_calls == [("support", {})]


@respx.mock
def test_reconcile_restarts_when_skill_version_changes(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    config = {"name": "support"}
    home = tmp_path / "agents" / "support"
    (home / "skills" / "alpha").mkdir(parents=True)
    (home / "skills" / "alpha" / "SKILL.md").write_text("old", encoding="utf-8")
    (home / "agent.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (home / ".node-skills.json").write_text(json.dumps({"alpha": "v1"}), encoding="utf-8")
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        json.dumps({"support": _config_hash_of(config)}), encoding="utf-8"
    )
    _status_route()
    backend = FakeBackend({"support": 12345})
    skill = DesiredSkill(
        name="alpha",
        version="v2",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"new"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired_with_skills([skill], config=config)
    )

    assert backend.stop_calls == ["support"]
    assert backend.spawn_calls == [("support", {})]
    assert (home / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "new"
    assert json.loads((home / ".node-skills.json").read_text()) == {"alpha": "v2"}


@respx.mock
def test_reconcile_keeps_running_when_config_and_skills_unchanged(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    config = {"name": "support"}
    home = tmp_path / "agents" / "support"
    (home / "skills" / "alpha").mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (home / ".node-skills.json").write_text(json.dumps({"alpha": "v1"}), encoding="utf-8")
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        json.dumps({"support": _config_hash_of(config)}), encoding="utf-8"
    )
    _status_route()
    backend = FakeBackend({"support": 12345})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"a"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired_with_skills([skill], config=config)
    )

    assert backend.stop_calls == []
    assert backend.spawn_calls == []


@respx.mock
def test_reconcile_cleans_removed_skill_but_keeps_unmanaged_dir(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    config = {"name": "support"}
    home = tmp_path / "agents" / "support"
    for name, body in (("alpha", "a"), ("beta", "b"), ("gamma", "builtin-copy")):
        (home / "skills" / name).mkdir(parents=True)
        (home / "skills" / name / "SKILL.md").write_text(body, encoding="utf-8")
    (home / "agent.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    # gamma is NOT node-managed (absent from manifest) — e.g. a builtin copy the agent materialized
    (home / ".node-skills.json").write_text(
        json.dumps({"alpha": "v1", "beta": "v1"}), encoding="utf-8"
    )
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        json.dumps({"support": _config_hash_of(config)}), encoding="utf-8"
    )
    _status_route()
    backend = FakeBackend({"support": 12345})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"a"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired_with_skills([skill], config=config)
    )

    assert (home / "skills" / "alpha" / "SKILL.md").exists()
    assert not (home / "skills" / "beta").exists()
    # unmanaged dir (not in node manifest) survives cleanup
    assert (home / "skills" / "gamma" / "SKILL.md").exists()
    assert json.loads((home / ".node-skills.json").read_text()) == {"alpha": "v1"}


@respx.mock
def test_reconcile_spawn_env_excludes_skills_dir_var(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    _status_route()
    backend = FakeBackend({"support": None})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"x"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired_with_skills([skill], secrets={"ANTHROPIC_API_KEY": "sk"})
    )

    _name, env = backend.spawn_calls[0]
    # agent run reads <home>/skills directly and ignores FLEETENT_SKILLS_DIR (agent_app.py),
    # so node MUST NOT inject it — spawn env carries only the agent's secrets.
    assert env == {"ANTHROPIC_API_KEY": "sk"}
    assert "FLEETENT_SKILLS_DIR" not in (env or {})


@respx.mock
def test_reconcile_removes_home_of_disappeared_agent_under_remote(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    (home / "skills" / "alpha").mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}), encoding="utf-8")
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        json.dumps({"support": "old-hash"}), encoding="utf-8"
    )
    _status_route()
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(
        DesiredState(node_id="node-a", agents=[], source="remote")
    )

    assert backend.stop_calls == ["support"]
    assert not home.exists()
    hashes = json.loads((state_dir / "applied-config-hashes.json").read_text())
    assert "support" not in hashes


@respx.mock
def test_reconcile_keeps_disappeared_agent_under_cache_source(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}), encoding="utf-8")
    _status_route()
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(
        DesiredState(node_id="node-a", agents=[], source="cache")
    )

    # cache fallback is non-authoritative: do not stop or delete a healthy local agent
    assert backend.stop_calls == []
    assert home.exists()


@respx.mock
def test_reconcile_remove_is_bulkheaded_when_stop_fails(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}), encoding="utf-8")
    status_route = _status_route()

    class BoomStopBackend(FakeBackend):
        def stop(self, agent_name: str) -> None:
            super().stop(agent_name)
            raise RuntimeError("stop failed")

    backend = BoomStopBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(
        DesiredState(node_id="node-a", agents=[], source="remote")
    )

    # stop raised but was bulkheaded: home still removed, status still posted
    assert backend.stop_calls == ["support"]
    assert not home.exists()
    assert status_route.called


@respx.mock
def test_reconcile_tolerates_corrupt_skill_manifest(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    config = {"name": "support"}
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (home / ".node-skills.json").write_text("{ not valid json", encoding="utf-8")
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        json.dumps({"support": _config_hash_of(config)}), encoding="utf-8"
    )
    status_route = _status_route()
    backend = FakeBackend({"support": 12345})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"a"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired_with_skills([skill], config=config)
    )

    # a corrupt manifest must not abort the whole reconcile loop; it degrades to "missing"
    # (-> treated as a skill change -> rewrite) and status is still posted.
    assert status_route.called
    assert json.loads((home / ".node-skills.json").read_text()) == {"alpha": "v1"}


@respx.mock
def test_reconcile_rejects_skill_file_path_escaping_skill_dir(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    _status_route()
    backend = FakeBackend({"support": None})
    skill = DesiredSkill(
        name="alpha",
        version="v1",
        files=[
            DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"ok")),
            DesiredSkillFile(path="../escape.txt", content_b64=_b64(b"evil")),
        ],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired_with_skills([skill]))

    skills_root = tmp_path / "agents" / "support" / "skills"
    assert (skills_root / "alpha" / "SKILL.md").read_bytes() == b"ok"
    # the traversal path is skipped — nothing written outside the skill dir
    assert not (skills_root / "escape.txt").exists()
    assert not (tmp_path / "agents" / "support" / "escape.txt").exists()


@respx.mock
def test_reconcile_rejects_skill_name_with_path_separator(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    _status_route()
    backend = FakeBackend({"support": None})
    bad = DesiredSkill(
        name="../evil",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"x"))],
    )
    good = DesiredSkill(
        name="alpha",
        version="v1",
        files=[DesiredSkillFile(path="SKILL.md", content_b64=_b64(b"ok"))],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired_with_skills([bad, good]))

    home = tmp_path / "agents" / "support"
    assert (home / "skills" / "alpha" / "SKILL.md").exists()
    # "../evil" would resolve to <home>/agents/support/evil — must be rejected entirely
    assert not (home / "evil").exists()
    assert json.loads((home / ".node-skills.json").read_text()) == {"alpha": "v1"}
