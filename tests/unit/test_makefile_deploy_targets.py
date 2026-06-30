from __future__ import annotations

from pathlib import Path


def test_makefile_exposes_production_deploy_targets_without_dev_home() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")

    for target in ("up", "down", "logs", "deploy", "redeploy", "deploy-status", "upgrade"):
        assert f"{target}:" in content
        assert (
            f"{target}: " in content and "##" in content.split(f"{target}: ", 1)[1].splitlines()[0]
        )

    assert "DEPLOY_FLEETENT_HOME ?= /srv/fleetent" in content
    assert "$(DEPLOY_TARGETS): export FLEETENT_HOME := $(DEPLOY_FLEETENT_HOME)" in content
    assert "$(COMPOSE) build --build-arg GIT_COMMIT=$(GIT_COMMIT)" in content
    assert "$(COMPOSE) up -d" in content
    assert "uv tool install --force" in content
    assert "restart your bare-metal fleetent services" in content
    assert "docker compose down -v" not in content
    assert "docker compose run --rm platform fleetent platform upgrade" in content


def test_makefile_dev_targets_use_shared_kb_service_config() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")

    assert "uv run fleetent kb-service init-config" in content
    assert "uv run fleetent kb-worker init-config" not in content
    assert "kb-serve" in content.split("DEV_TARGETS :=", 1)[1]
    assert "make platform', 'make node', 'make kb-worker', 'make kb-serve'" in content
    assert (
        "uv run fleetent kb-worker --config $(FLEETENT_HOME)/kb-service/default/kb-service.yaml"
        in content
    )
    assert (
        "uv run fleetent kb-serve --config $(FLEETENT_HOME)/kb-service/default/kb-service.yaml"
        in content
    )
