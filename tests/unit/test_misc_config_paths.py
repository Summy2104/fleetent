"""Agent runtime paths derive from the resolver.

Note: ``admin_cli.init_config`` is intentionally excluded — its file/dir lists
are a scaffold layout relative to an operator-chosen ``root`` argument, not
runtime path resolution, so they must stay relative.
"""

from fleetent import agent_config, paths


def test_runtime_config_paths_derive_from_resolver(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    assert paths.agents_dir() == agent_config.AGENTS_DIR
