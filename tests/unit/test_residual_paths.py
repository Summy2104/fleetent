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


def test_dev_stack_makefile_uses_tenant_first_paths() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "DATABASE_URL  ?= sqlite:///$(FLEETENT_HOME)/management.db" in makefile
    assert '--home "$(FLEETENT_HOME)/tenants/default/agents/$(AGENT)"' in makefile
    assert "$(FLEETENT_HOME)/data/management.db" not in makefile
    assert "$(FLEETENT_HOME)/agents/$(AGENT)" not in makefile


def test_installers_initialize_root_management_db() -> None:
    offenders: list[str] = []
    for script in (Path("scripts/install.sh"), Path("scripts/install-platform.sh")):
        content = script.read_text(encoding="utf-8")
        if "$FLEETENT_HOME/data/management.db" in content:
            offenders.append(f"{script}: $FLEETENT_HOME/data/management.db")
        if "sqlite:///$FLEETENT_HOME/management.db" not in content:
            offenders.append(f"{script}: missing root management.db URL")

    assert not offenders, "installers still use legacy management DB path:\n" + "\n".join(offenders)
