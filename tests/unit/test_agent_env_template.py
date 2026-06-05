"""The agent .env template is process-level only — agent secrets are materialized."""

from pathlib import Path

_ENV_EXAMPLE = (
    Path(__file__).resolve().parents[2] / "config" / "agent" / ".env.example"
).read_text(encoding="utf-8")


def test_includes_secret_key_and_process_level_vars():
    assert "FLEETENT_SECRET_KEY=" in _ENV_EXAMPLE
    assert "MICROSANDBOX_URL=" in _ENV_EXAMPLE
    assert "LOG_FORMAT=" in _ENV_EXAMPLE


def test_agent_referenced_secrets_removed():
    # these now come from materialize (per-agent) + the console panel, not the template
    for name in (
        "FLEETENT_MODEL_PRIMARY_API_KEY",
        "SUPPORT_SLACK_BOT",
        "ACME_DOCS_MCP_TOKEN",
        "GITHUB_MCP_API_KEY",
        "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
        "FLEETENT_CONFLUENCE_TOKEN",
    ):
        assert name not in _ENV_EXAMPLE, name


def test_no_secret_value_is_inlined():
    for line in _ENV_EXAMPLE.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_KEY", "_DSN")):
            assert value == "", f"{key} must not inline a value"
