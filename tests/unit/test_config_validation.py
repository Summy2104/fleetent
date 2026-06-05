import json


def test_env_provided_secret_values_are_not_inline_config_errors(monkeypatch):
    from fleetent.config import Settings
    from fleetent.platform.config_validation import validate_config

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-1234567890abcdef")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789012345678901234")
    settings = Settings()

    report = validate_config(profile="pilot", settings=settings, config_paths=[])

    assert report.final_status != "error"
    assert not [item for item in report.items if item.key.startswith("settings.slack")]
    assert "xoxb-1234567890abcdef" not in report.to_json()


def test_secret_like_values_in_config_files_are_errors(tmp_path):
    from fleetent.config import Settings
    from fleetent.platform.config_validation import validate_config

    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text("image_gen_url: sk-ant-1234567890abcdef\n", encoding="utf-8")

    report = validate_config(
        profile="pilot",
        settings=Settings(),
        config_paths=[settings_file],
    )

    secret_items = [
        item for item in report.items if item.key == f"config.{settings_file}.image_gen_url"
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


def test_inline_secret_like_config_values_are_errors():
    from fleetent.config import Settings
    from fleetent.platform.config_validation import validate_config

    settings = Settings(image_gen_url="sk-ant-1234567890abcdef")

    report = validate_config(profile="pilot", settings=settings, scan_resolved_settings=True)

    secret_items = [item for item in report.items if item.key == "settings.image_gen_url"]
    assert secret_items
    assert secret_items[0].status == "error"
    assert "inline secret-like value" in secret_items[0].reason


def test_profile_rules_warn_skip_or_error_for_production_dependencies():
    from fleetent.config import Settings
    from fleetent.platform.config_validation import validate_config

    settings = Settings(embedding={"backend": "deterministic"})

    dev = validate_config(profile="dev", settings=settings)
    pilot = validate_config(profile="pilot", settings=settings)
    production = validate_config(profile="production", settings=settings)

    assert _item(dev, "embedding.backend").status == "warning"
    assert _item(pilot, "embedding.backend").status == "skipped"
    assert _item(production, "embedding.backend").status == "error"


def _item(report, key):
    return next(item for item in report.items if item.key == key)
