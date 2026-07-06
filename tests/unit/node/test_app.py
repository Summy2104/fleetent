from __future__ import annotations

from types import SimpleNamespace

import pytest

from fleetent.node.config import ConfigError, NodeConfig
from fleetent.node.provider import DesiredState


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def test_main_loops_fetch_reconcile_and_report(monkeypatch, tmp_path) -> None:
    from fleetent.node import app

    desired = DesiredState(node_id="node-a", agents=[])
    calls: list[str] = []

    class FakeProvider:
        def fetch(self) -> DesiredState:
            calls.append("fetch")
            return desired

    class FakeReconciler:
        def reconcile(self, received: DesiredState) -> None:
            assert received is desired
            calls.append("reconcile")

    monkeypatch.setattr(app, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(app, "PlatformApiDesiredStateProvider", lambda config: FakeProvider())
    backend = object()
    monkeypatch.setattr(app, "create_process_backend", lambda config: backend)
    monkeypatch.setattr(app, "NodeReconciler", lambda config, backend: FakeReconciler())
    monkeypatch.setattr(
        app,
        "_start_forwarder",
        lambda config, backend: (
            SimpleNamespace(should_exit=False),
            SimpleNamespace(join=lambda timeout=0: None),
        ),
    )

    def stop_after_first_sleep(seconds: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(app.time, "sleep", stop_after_first_sleep)

    app.main()

    assert calls == ["fetch", "reconcile"]


def test_node_app_does_not_host_im_edge(monkeypatch, tmp_path) -> None:
    """agent-hosted-im (Group 5): node exits the IM data plane — no NodeIMEdgeHost, no
    IM supervisor, no outbound drain. The agent self-hosts its own IM connection."""
    from fleetent.node import app

    # The module must no longer reference a node-hosted IM edge host at all.
    assert not hasattr(app, "NodeIMEdgeHost")

    desired = DesiredState(node_id="node-a", agents=[])

    class FakeProvider:
        def fetch(self) -> DesiredState:
            return desired

    class FakeReconciler:
        def reconcile(self, received: DesiredState) -> None:
            pass

    monkeypatch.setattr(app, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(app, "PlatformApiDesiredStateProvider", lambda config: FakeProvider())
    monkeypatch.setattr(app, "create_process_backend", lambda config: object())
    monkeypatch.setattr(app, "NodeReconciler", lambda config, backend: FakeReconciler())
    monkeypatch.setattr(
        app,
        "_start_forwarder",
        lambda config, backend: (
            SimpleNamespace(should_exit=False),
            SimpleNamespace(join=lambda timeout=0: None),
        ),
    )
    monkeypatch.setattr(app.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt))

    # Must run the reconcile loop with no IM-edge host in the picture (no exception).
    app.main()


def test_main_exits_on_invalid_config(monkeypatch) -> None:
    from fleetent.node import app

    monkeypatch.setattr(app, "load_config", lambda: (_ for _ in ()).throw(ConfigError("missing")))

    with pytest.raises(SystemExit, match="1"):
        app.main()


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, {"log_format": "console"}),
        ({"LOG_FORMAT": "json", "LOG_LEVEL": "debug"}, {"log_format": "json"}),
    ],
)
def test_main_configures_process_logging_from_env(monkeypatch, tmp_path, env, expected) -> None:
    from fleetent.node import app

    desired = DesiredState(node_id="node-a", agents=[])

    class FakeProvider:
        def fetch(self) -> DesiredState:
            return desired

    class FakeReconciler:
        def reconcile(self, received: DesiredState) -> None:
            assert received is desired

    for key in ("LOG_FORMAT", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    logging_calls: list[dict[str, object]] = []
    monkeypatch.setattr(app, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(app, "PlatformApiDesiredStateProvider", lambda config: FakeProvider())
    monkeypatch.setattr(app, "create_process_backend", lambda config: object())
    monkeypatch.setattr(app, "NodeReconciler", lambda config, backend: FakeReconciler())
    monkeypatch.setattr(
        app,
        "_start_forwarder",
        lambda config, backend: (
            SimpleNamespace(should_exit=False),
            SimpleNamespace(join=lambda timeout=0: None),
        ),
    )
    monkeypatch.setattr(
        "fleetent.logging_setup.setup_process_logging",
        lambda **kwargs: logging_calls.append(kwargs),
    )
    monkeypatch.setattr(app.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt))
    monkeypatch.setattr("fleetent.build_info.log_service_startup", lambda name: None)

    app.main()

    assert len(logging_calls) == 1
    assert logging_calls[0]["log_format"] == expected["log_format"]
