from pathlib import Path


def test_pilot_install_checklist_exists_and_covers_required_sections():
    checklist = Path("docs/deployment/pilot-install-checklist.md")

    assert checklist.exists()
    content = checklist.read_text(encoding="utf-8")

    required_sections = [
        "## 适用范围",
        "## 前置条件",
        "## 配置与 Secret 边界",
        "## 安装、升级与备份",
        "## 启动与健康检查",
        "## Knowledge Base Connector 验证",
        "## Observability 查询",
        "## Diagnostics 与 Retention",
        "## 回滚",
        "## Pilot 验收清单",
        "## 问题上报包",
    ]
    for section in required_sections:
        assert section in content


def test_pilot_install_checklist_contains_required_commands():
    content = Path("docs/deployment/pilot-install-checklist.md").read_text(encoding="utf-8")

    required_commands = [
        "uv sync",
        "uv run python scripts/upgrade.py --dry-run",
        "alembic upgrade head",
        "uv run uvicorn fleetent.server:app",
        "GET /health",
        "uv run fleetent-admin kb connectors list",
        "uv run fleetent-admin kb connectors check",
        "uv run fleetent-admin kb connectors sync",
        "uv run fleetent-admin kb connectors status",
        "uv run fleetent-admin observability traces",
        "uv run fleetent-admin observability usage",
        "uv run fleetent-admin observability performance",
        "uv run fleetent-admin diagnostics export",
        "uv run fleetent-admin diagnostics retention dry-run",
    ]
    for command in required_commands:
        assert command in content


def test_pilot_install_checklist_documents_secret_and_reporting_boundaries():
    content = Path("docs/deployment/pilot-install-checklist.md").read_text(encoding="utf-8")

    required_phrases = [
        "不要把真实 secret、token、credential payload 写入 settings、日志、trace",
        "diagnostics package、issue 或测试 fixture",
        "credential_ref",
        "SQLite backup",
        "停止 fleetent 服务",
        "替换当前 DB 文件",
        "重启 fleetent 服务",
        "问题上报包",
        "不包含真实 secret",
    ]
    for phrase in required_phrases:
        assert phrase in content
