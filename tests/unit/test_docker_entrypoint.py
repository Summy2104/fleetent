from pathlib import Path


def test_docker_entrypoint_auto_upgrade_is_explicit_opt_in():
    content = Path("scripts/docker_entrypoint.sh").read_text(encoding="utf-8")

    assert "${FLEETENT_AUTO_UPGRADE:-false}" in content
    assert '= "true"' in content
    assert "fleetent platform upgrade" in content
    assert content.index("fleetent platform upgrade") < content.index(
        "exec fleetent platform serve"
    )
    assert 'role="${1:-platform}"' in content


def test_docker_entrypoint_routes_kb_role():
    """Compose runs KB services as `command: ["kb", "worker"|"serve", ...]` — the
    entrypoint must route the `kb` role to `fleetent kb <subcommand>`, otherwise
    both containers exit 64 with "unsupported role"."""
    content = Path("scripts/docker_entrypoint.sh").read_text(encoding="utf-8")

    assert "kb)" in content
    assert 'exec fleetent kb "$@"' in content


def test_compose_kb_commands_match_entrypoint_roles():
    """Every compose service command's first token must be a role the entrypoint
    accepts — this is the seam that broke when the CLI regrouped kb verbs."""
    import re

    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = Path("scripts/docker_entrypoint.sh").read_text(encoding="utf-8")

    roles = set(re.findall(r"^\s{2}([a-z-]+)\)", entrypoint, flags=re.MULTILINE))
    first_tokens = set(re.findall(r'command: \["([a-z-]+)"', compose))
    assert first_tokens, "expected compose service commands"
    assert first_tokens <= roles, f"compose commands {first_tokens} not in entrypoint roles {roles}"
