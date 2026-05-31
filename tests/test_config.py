import pytest

from fleetent.config import Settings, configure_logging


def test_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.permission_gate_medium_timeout_seconds == 300
    assert s.permission_gate_high_timeout_seconds == 3600


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("PERMISSION_GATE_MEDIUM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    assert s.permission_gate_medium_timeout_seconds == 120


def test_settings_missing_required_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here — prevents pydantic-settings from loading it
    with pytest.raises(Exception):  # noqa: B017
        Settings()


def test_configure_logging_does_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    configure_logging(s)  # should not raise


def test_configure_logging_then_log_does_not_raise(monkeypatch):
    # Regression: add_logger_name read logger.name, but PrintLoggerFactory loggers
    # have no .name, so EVERY log call crashed after configure_logging() ran.
    import structlog

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    try:
        configure_logging(Settings())
        structlog.get_logger("test").info("hello", k="v")  # must not raise
    finally:
        structlog.reset_defaults()


def test_default_agent_name_defaults_to_none():
    s = Settings(anthropic_api_key="test-key")
    assert s.default_agent_name is None


def test_default_agent_name_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_AGENT_NAME", "basic")
    s = Settings()
    assert s.default_agent_name == "basic"


def test_context_dual_threshold_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.context_tmax_ratio == 0.8
    assert s.context_tretained_ratio == 0.6


def test_context_dual_threshold_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CONTEXT_TMAX_RATIO", "0.9")
    monkeypatch.setenv("CONTEXT_TRETAINED_RATIO", "0.5")
    s = Settings()
    assert s.context_tmax_ratio == 0.9
    assert s.context_tretained_ratio == 0.5


def test_context_initial_intent_max_default():
    s = Settings(anthropic_api_key="test-key")
    assert s.compression_initial_intent_max == 2


def test_context_initial_intent_max_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("COMPRESSION_INITIAL_INTENT_MAX", "3")
    s = Settings()
    assert s.compression_initial_intent_max == 3


def test_context_compress_threshold_removed():
    s = Settings(anthropic_api_key="test-key")
    assert not hasattr(s, "context_compress_threshold")


def test_agent_loop_repeat_threshold_default():
    s = Settings(anthropic_api_key="test-key")
    assert s.agent_loop_repeat_threshold == 3


def test_agent_loop_repeat_threshold_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOOP_REPEAT_THRESHOLD", "5")
    s = Settings()
    assert s.agent_loop_repeat_threshold == 5


def test_loop_detect_ignore_arg_keys_default_empty():
    s = Settings(anthropic_api_key="test-key")
    assert s.loop_detect_ignore_arg_keys == []


def test_image_gen_url_default_empty():
    s = Settings(anthropic_api_key="test-key")
    assert s.image_gen_url == ""


def test_image_gen_url_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_GEN_URL", "http://localhost:9000/v1/")
    s = Settings()
    assert s.image_gen_url == "http://localhost:9000/v1/"


def test_image_gen_model_default():
    s = Settings(anthropic_api_key="test-key")
    assert s.image_gen_model == "default"


def test_image_gen_model_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_GEN_MODEL", "sdxl")
    s = Settings()
    assert s.image_gen_model == "sdxl"


def test_budget_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.agent_max_tokens == -1
    assert s.agent_max_cost_usd == -1.0
    assert s.agent_grace_call_token_ratio == 0.05
    assert s.agent_grace_call_min_tokens == 512


def test_budget_settings_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MAX_TOKENS", "100000")
    monkeypatch.setenv("AGENT_MAX_COST_USD", "2.5")
    monkeypatch.setenv("AGENT_GRACE_CALL_TOKEN_RATIO", "0.1")
    monkeypatch.setenv("AGENT_GRACE_CALL_MIN_TOKENS", "256")
    s = Settings()
    assert s.agent_max_tokens == 100000
    assert s.agent_max_cost_usd == 2.5
    assert s.agent_grace_call_token_ratio == 0.1
    assert s.agent_grace_call_min_tokens == 256
