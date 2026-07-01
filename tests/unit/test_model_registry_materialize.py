"""Unit tests for model-registry materialize join and fallback paths."""

from fleetent.agent_config import default_models
from fleetent.platform.agent_lifecycle import materialize


class _LoggerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def warn(self, event: str, **kwargs: object) -> None:
        self.calls.append((event, kwargs))


def test_target_from_model_override_joins_model_and_provider(monkeypatch):
    monkeypatch.setattr(
        materialize.model_admin_store,
        "get_model",
        lambda model_id: {
            "id": model_id,
            "provider_id": "anthropic-shared",
            "protocol": "openai_chat",
            "model_name": "claude-sonnet-4-5",
            "base_url": "https://api.anthropic.example/v1",
            "endpoint": None,
            "max_tokens": 4096,
            "params": {"temperature": 0.2, "reasoning_effort": "medium"},
            "extra_params": {"top_p": 0.9},
        },
    )
    monkeypatch.setattr(
        materialize.provider_admin_store,
        "get_provider",
        lambda provider_id: {
            "id": provider_id,
            "vendor": "anthropic",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
    )

    target = materialize._target_from_model_override(
        "default",
        0,
        {"model_id": "claude-sonnet", "max_tokens": 2048, "params": {"temperature": 0.1}},
    )

    assert target.id == "claude-sonnet"
    assert target.provider == "anthropic"
    assert target.protocol == "openai_chat"
    assert target.base_url == "https://api.anthropic.example/v1"
    assert target.model == "claude-sonnet-4-5"
    assert target.api_key_env == "ANTHROPIC_API_KEY"
    assert target.max_tokens == 2048
    assert target.params == {"temperature": 0.1, "reasoning_effort": "medium"}


def test_target_from_model_override_falls_back_to_inline_legacy_shape(monkeypatch):
    logger = _LoggerStub()
    monkeypatch.setattr(materialize, "_logger", logger)
    monkeypatch.setattr(materialize.model_admin_store, "get_model", lambda model_id: None)

    target = materialize._target_from_model_override(
        "default",
        0,
        {
            "provider_id": "legacy-inline",
            "provider": "anthropic",
            "protocol": "openai_chat",
            "base_url": "https://api.anthropic.example/v1",
            "model": "claude-opus",
            "api_key_env": "LEGACY_ENV",
            "params": {"temperature": 0.2},
        },
    )

    assert target.id == "legacy-inline"
    assert target.provider == "anthropic"
    assert target.api_key_env == "LEGACY_ENV"
    assert target.model == "claude-opus"
    assert logger.calls


def test_models_from_overrides_preserves_route_order_and_entry_overrides(monkeypatch):
    monkeypatch.setattr(
        materialize.model_admin_store,
        "get_model",
        lambda model_id: {
            "id": model_id,
            "provider_id": f"{model_id}-provider",
            "protocol": "http_embedding" if model_id.startswith("embed") else "openai_chat",
            "model_name": model_id,
            "base_url": None if model_id.startswith("embed") else "https://chat.example/v1",
            "endpoint": "https://embed.example/v1" if model_id.startswith("embed") else None,
            "max_tokens": 8192,
            "params": {"temperature": 0.3},
            "extra_params": None,
        },
    )
    monkeypatch.setattr(
        materialize.provider_admin_store,
        "get_provider",
        lambda provider_id: {
            "id": provider_id,
            "vendor": provider_id.replace("-provider", ""),
            "api_key_env": f"{provider_id.upper().replace('-', '_')}_KEY",
        },
    )

    models = materialize._models_from_overrides(
        {
            "default": [
                {"model_id": "chat-primary"},
                {"model_id": "chat-fallback", "max_tokens": 1024, "params": {"temperature": 0.1}},
            ],
            "embedding": {"model_id": "embed-main", "params": {"dimensions": 768}},
        }
    )

    assert [entry.target for entry in models.routes["default"]] == ["chat-primary", "chat-fallback"]
    assert models.routes["default"][1].max_tokens == 1024
    assert models.routes["default"][1].params == {"temperature": 0.1}
    assert models.routes["embedding"][0].target == "embed-main"
    assert models.routes["embedding"][0].params == {"dimensions": 768}


def test_models_from_overrides_keeps_unconfigured_routes_at_baseline(monkeypatch):
    monkeypatch.setattr(
        materialize.model_admin_store,
        "get_model",
        lambda model_id: {
            "id": model_id,
            "provider_id": "custom-provider",
            "protocol": "openai_chat",
            "model_name": "custom-chat-model",
            "base_url": "https://chat.example/v1",
            "endpoint": None,
            "max_tokens": 4096,
            "params": {},
            "extra_params": None,
        },
    )
    monkeypatch.setattr(
        materialize.provider_admin_store,
        "get_provider",
        lambda provider_id: {
            "id": provider_id,
            "vendor": "custom",
            "api_key_env": "CUSTOM_API_KEY",
        },
    )

    models = materialize._models_from_overrides({"default": [{"model_id": "custom-chat"}]})
    baseline = default_models()

    assert [entry.target for entry in models.routes["default"]] == ["custom-chat"]
    assert models.routes["memory_extraction"] == baseline.routes["memory_extraction"]
    assert models.routes["kb_extraction"] == baseline.routes["kb_extraction"]
    assert models.routes["vision"] == baseline.routes["vision"]
    assert models.routes["embedding"] == baseline.routes["embedding"]
    assert {target.id for target in models.targets} == {
        "custom-chat",
        "default",
        "vision",
        "embedding",
    }


def test_models_from_overrides_drops_baseline_target_once_all_its_routes_are_overridden(
    monkeypatch,
):
    monkeypatch.setattr(
        materialize.model_admin_store,
        "get_model",
        lambda model_id: {
            "id": model_id,
            "provider_id": "custom-provider",
            "protocol": "openai_chat",
            "model_name": "custom-chat-model",
            "base_url": "https://chat.example/v1",
            "endpoint": None,
            "max_tokens": 4096,
            "params": {},
            "extra_params": None,
        },
    )
    monkeypatch.setattr(
        materialize.provider_admin_store,
        "get_provider",
        lambda provider_id: {
            "id": provider_id,
            "vendor": "custom",
            "api_key_env": "CUSTOM_API_KEY",
        },
    )

    models = materialize._models_from_overrides(
        {
            "default": [{"model_id": "custom-chat"}],
            "memory_extraction": [{"model_id": "custom-chat"}],
            "kb_extraction": [{"model_id": "custom-chat"}],
        }
    )

    target_ids = {target.id for target in models.targets}
    # The baseline "default" target is no longer referenced by any route (default/memory_extraction/
    # kb_extraction were all overridden), so it must be dropped rather than lingering unused.
    assert "default" not in target_ids
    # vision/embedding routes were untouched, so their baseline targets stay.
    assert {"vision", "embedding", "custom-chat"} <= target_ids
