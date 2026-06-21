from __future__ import annotations

import yaml

import fleetent.agent_config as agent_config
import fleetent.agent_store as agent_store
import fleetent.platform.agent_lifecycle.materialize as materialize
import fleetent.platform.agent_management_console.agent_admin_store as agent_admin_store
from scripts import upgrade
from tests.integration._migration_template import apply_migrations


def test_existing_file_default_backfilled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "management.db"
    agents_dir = tmp_path / "agents"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))
    apply_migrations(db_path)
    agent = agent_store.create_agent("basic", "Basic.", ["shell"])
    agent_dir = agents_dir / "basic"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "basic",
                "version": 1,
                "models": agent_config.default_models().model_dump(mode="json"),
                "bindings": {"default": True},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    upgrade.backfill_default_agents(db_path, agents_dir)

    assert agent_admin_store.get_state(agent.id)["is_default"] == 1
    payload = materialize.agent_file_from_store(agent).model_dump(
        mode="json", exclude_defaults=False
    )
    assert payload["bindings"]["default"] is True
