"""Agent/cron/model runtime config paths derive from the resolver.

Note: ``admin_cli.init_config`` is intentionally excluded — its file/dir lists
are a scaffold layout relative to an operator-chosen ``root`` argument, not
runtime path resolution, so they must stay relative.
"""

from fleetent import agent_config, cron_scheduler, paths
from fleetent.model import router


def test_runtime_config_paths_derive_from_resolver(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    assert paths.config_dir() / "agents" == agent_config.AGENTS_DIR
    assert paths.config_dir() / "cron.yaml" == cron_scheduler.LEGACY_CRON_CONFIG_PATH
    assert paths.config_dir() / "routes.yaml" == router.ROUTES_PATH
