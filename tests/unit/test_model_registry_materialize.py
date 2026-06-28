"""Unit tests for model-registry materialize join and fallback paths."""

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
