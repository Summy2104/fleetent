from pathlib import Path


def test_pilot_runbook_documents_validation_gate_and_manual_maintenance_boundaries():
    runbook = Path("docs/operations/pilot-runbook.md").read_text(encoding="utf-8")

    for expected in [
        "uv run fleetent-admin validate-config --profile pilot --format json",
        (
            "diagnostics package 不包含 SQLite 主库、备份、secret 文件、完整 prompt/reply "
            "或 KB document body"
        ),
        "uv run python scripts/generate_pilot_verification_report.py",
        "execute sync 必须额外 opt-in，且只允许 Pilot fixture 目录或空间",
        "maintenance 命令必须先 dry-run；apply / rebuild / delete / approve / reject 必须带 --yes",
    ]:
        assert expected in runbook
