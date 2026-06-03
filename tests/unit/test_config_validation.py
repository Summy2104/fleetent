import json


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

    settings = Settings(anthropic_api_key="", image_gen_url="sk-ant-1234567890abcdef")

    report = validate_config(profile="pilot", settings=settings)

    secret_items = [item for item in report.items if item.key == "settings.image_gen_url"]
    assert secret_items
    assert secret_items[0].status == "error"
    assert "inline secret-like value" in secret_items[0].reason


def test_profile_rules_warn_skip_or_error_for_production_dependencies():
    from fleetent.config import Settings
    from fleetent.platform.config_validation import validate_config

    settings = Settings(anthropic_api_key="", embedding={"backend": "deterministic"})

    dev = validate_config(profile="dev", settings=settings)
    pilot = validate_config(profile="pilot", settings=settings)
    production = validate_config(profile="production", settings=settings)

    assert _item(dev, "embedding.backend").status == "warning"
    assert _item(pilot, "embedding.backend").status == "skipped"
    assert _item(production, "embedding.backend").status == "error"


def _item(report, key):
    return next(item for item in report.items if item.key == key)
