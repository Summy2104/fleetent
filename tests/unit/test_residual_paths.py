"""Residual fallback defaults also derive from the resolver (no CWD-relative leak)."""

from pathlib import Path

import pytest

from fleetent import structured_logging


def test_logging_config_default_directory_follows_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert structured_logging._LoggingConfig().directory == tmp_path / "data" / "logs"


def test_diagnostics_default_data_dir_follows_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fleetent import paths
    from fleetent.observability import diagnostics

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    # The module no longer hardcodes a CWD-relative "data" fallback.
    assert diagnostics._default_data_dir() == paths.data_dir()


def test_tenant_first_docs_do_not_refer_to_legacy_canonical_paths() -> None:
    docs = {
        Path("docs/architecture/data-model.md"): [
            "data/<tenant>/<agent>",
            "<tenant>/<agent_id>/",
        ],
        Path("docs/architecture/target-architecture.md"): [
            "<tenant>/<agent_id>/",
            "materialize 进 `agent.yaml`（推）",
        ],
        Path("docs/capabilities/agent-management.md"): [
            "materialize_from_store(name)",
            "<FLEETENT_HOME>/agents/<name>/agent.yaml",
            (
                "平台侧把 agent 的**定义 + 管理态 + 绑定**维护在管理库，经 "
                "**materialize** 单向刷成 agent 侧 `agent.yaml`"
            ),
        ],
        Path("docs/capabilities/skill-system.md"): [
            "经 **materialize** 单向同步进 agent.yaml + agent home",
            "materialize `_copy_skills()`",
            "其余绑定该 skill 的 agent 下次 materialize 拿新版本",
        ],
        Path("docs/capabilities/config-management.md"): [
            "sqlite:///data/management.db",
            "data/management.db",
        ],
    }

    offenders: list[str] = []
    for doc, patterns in docs.items():
        content = doc.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in content:
                offenders.append(f"{doc}: {pattern}")

    assert not offenders, (
        "tenant-first docs still mention legacy/platform-write contracts:\n" + "\n".join(offenders)
    )
