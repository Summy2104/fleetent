from __future__ import annotations


def test_build_commit_defaults_to_unknown(monkeypatch) -> None:
    from fleetent import build_info

    monkeypatch.delenv("FLEETENT_BUILD_COMMIT", raising=False)

    assert build_info.build_commit() == "unknown"


def test_log_service_startup_includes_build_commit(monkeypatch) -> None:
    from fleetent import build_info

    events: list[tuple[str, dict[str, str]]] = []

    class FakeLogger:
        def info(self, message: str, **fields: str) -> None:
            events.append((message, fields))

    monkeypatch.setenv("FLEETENT_BUILD_COMMIT", "5dc87584")
    monkeypatch.setattr(build_info, "get_logger", lambda component: FakeLogger())

    build_info.log_service_startup("platform")

    assert events == [
        ("service_startup", {"service": "platform", "build_commit": "5dc87584"})
    ]
