from __future__ import annotations

from pathlib import Path


def agent_home_dir(home_dir: Path, agent_name: str, *, tenant_id: str = "default") -> Path:
    return home_dir / "tenants" / tenant_id / "agents" / agent_name


def agent_state_db_path(home_dir: Path, agent_name: str, *, tenant_id: str = "default") -> Path:
    return agent_home_dir(home_dir, agent_name, tenant_id=tenant_id) / "data" / "agent_state.db"
