import json


def test_env_provided_secret_values_are_not_inline_config_errors(monkeypatch):
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.platform.config_validation import validate_config

    # The agent references its Slack token by env-var name; the secret value lives in
    # the environment and never appears in agent.yaml or the validation output.
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-1234567890abcdef")
    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        connectors={"slack": {"bot_token_env": "SLACK_BOT_TOKEN", "app_token_env": "SLACK_APP"}},
    )

    report = validate_config(
        profile="pilot", agent=agent, config_paths=[], scan_resolved_agent=True
    )

    assert "xoxb-1234567890abcdef" not in report.to_json()


def test_secret_like_values_in_config_files_are_errors(tmp_path):
    from fleetent.platform.config_validation import validate_config

    agent_yaml = tmp_path / "agent.yaml"
    agent_yaml.write_text("image_gen_url: sk-ant-1234567890abcdef\n", encoding="utf-8")

    report = validate_config(profile="pilot", config_paths=[agent_yaml])

    secret_items = [
        item for item in report.items if item.key == f"config.{agent_yaml}.image_gen_url"
    ]
    assert secret_items
    assert secret_items[0].status == "error"


def test_validation_report_serializes_stable_status_summary():
    from fleetent.platform.config_validation import ValidationItem, ValidationReport

    report = ValidationReport(
        profile="pilot",
        items=[
            ValidationItem("database.url", "pass", "database URL is configured"),
            ValidationItem("real_smoke.google_drive", "skipped", "credential_ref is absent"),
        ],
    )

    payload = json.loads(report.to_json())
    assert payload == {
        "final_status": "pass",
        "items": [
            {
                "key": "database.url",
                "reason": "database URL is configured",
                "status": "pass",
            },
            {
                "key": "real_smoke.google_drive",
                "reason": "credential_ref is absent",
                "status": "skipped",
            },
        ],
        "profile": "pilot",
        "summary": {"error": 0, "pass": 1, "skipped": 1, "warning": 0},
    }


def test_inline_secret_like_agent_values_are_errors():
    from fleetent.agent_config import AgentFile
    from fleetent.platform.config_validation import validate_config

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "primary",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://local.test/v1/",
                        "model": "text",
                        "api_key_env": "sk-ant-1234567890abcdef",
                    }
                ],
                "routes": {"default": [{"target": "primary"}]},
            },
        }
    )

    report = validate_config(profile="pilot", agent=agent, scan_resolved_agent=True)

    secret_items = [
        item for item in report.items if item.key == "agent.models.targets.0.api_key_env"
    ]
    assert secret_items
    assert secret_items[0].status == "error"
    assert "inline secret-like value" in secret_items[0].reason


def test_profile_rules_warn_skip_or_error_for_production_dependencies():
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.platform.config_validation import validate_config

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        embedding={"backend": "deterministic"},
    )

    dev = validate_config(profile="dev", agent=agent)
    pilot = validate_config(profile="pilot", agent=agent)
    production = validate_config(profile="production", agent=agent)

    assert _item(dev, "embedding.backend").status == "warning"
    assert _item(pilot, "embedding.backend").status == "skipped"
    assert _item(production, "embedding.backend").status == "error"


def _item(report, key):
    return next(item for item in report.items if item.key == key)
