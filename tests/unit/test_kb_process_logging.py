from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def test_serve_main_configures_process_logging_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fleetent.knowledge_base import serve

    config_path = tmp_path / "kb-service.yaml"
    config_path.write_text("service: {}\n", encoding="utf-8")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    logging_calls: list[dict[str, object]] = []
    host_config = SimpleNamespace(
        service=SimpleNamespace(service_key_ref="svc", host="127.0.0.1", port=8768),
        retrieval=SimpleNamespace(default_mode="hybrid"),
        configure_process_runtime=lambda: None,
    )
    monkeypatch.setattr(
        "fleetent.logging_setup.setup_process_logging",
        lambda **kwargs: logging_calls.append(kwargs),
    )
    monkeypatch.setattr(serve, "create_app", lambda config: {"config": config})
    monkeypatch.setattr(
        "fleetent.knowledge_base.service_config.load_host_service_config",
        lambda path: host_config,
    )
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)

    serve.main(["--config", str(config_path)])

    assert len(logging_calls) == 1
    assert logging_calls[0]["log_format"] == "json"


def test_worker_main_configures_process_logging_with_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.knowledge_base import worker

    for key in ("LOG_FORMAT", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)

    logging_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "fleetent.logging_setup.setup_process_logging",
        lambda **kwargs: logging_calls.append(kwargs),
    )
    monkeypatch.setattr(worker, "load_config", lambda: worker.KBWorkerConfig())
    monkeypatch.setattr(worker, "run", lambda **kwargs: None)
    monkeypatch.setattr("fleetent.build_info.log_service_startup", lambda name: None)

    worker.main([])

    assert len(logging_calls) == 1
    assert logging_calls[0]["log_format"] == "console"
