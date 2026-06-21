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
    monkeypatch.setattr(app, "LocalProcessBackend", lambda config: object())
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


def test_main_exits_on_invalid_config(monkeypatch) -> None:
    from fleetent.node import app

    monkeypatch.setattr(app, "load_config", lambda: (_ for _ in ()).throw(ConfigError("missing")))

    with pytest.raises(SystemExit, match="1"):
        app.main()
