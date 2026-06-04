import pytest

from fleetent.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))


def test_settings_env_overrides_settings_yaml(tmp_path, monkeypatch):
    import fleetent.config as cfg

    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        "\n".join(
            [
                "database_url: sqlite:///tmp/from-yaml.db",
                "log_format: json",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/from-env.db")

    s = Settings()

    assert s.database_url == "sqlite:///tmp/from-env.db"
    assert s.log_format == "json"
