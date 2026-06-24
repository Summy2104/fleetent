from pathlib import Path


def test_docker_entrypoint_auto_upgrade_is_explicit_opt_in():
    content = Path("scripts/docker_entrypoint.sh").read_text(encoding="utf-8")

    assert "${FLEETENT_AUTO_UPGRADE:-false}" in content
    assert '= "true"' in content
    assert "uv run fleetent platform upgrade" in content
    assert content.index("uv run fleetent platform upgrade") < content.index(
        "exec uv run fleetent platform serve"
    )
