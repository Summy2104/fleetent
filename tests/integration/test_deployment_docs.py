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


def test_pilot_runbook_exists_and_covers_step_by_step_flow():
    runbook = Path("docs/deployment/pilot-runbook.md")

    assert runbook.exists()
    content = runbook.read_text(encoding="utf-8")

    required_sections = [
        "## 0. 准备验收记录",
        "## 1. 确认代码版本和工作区",
        "## 2. 准备配置和 Secret",
        "## 3. 安装依赖",
        "## 4. SQLite Dry-run、备份和升级",
        "## 5. 启动服务和基础 Health Check",
        "## 6. Observability 和 Diagnostics",
        "## 7. Memory 验收",
        "## 8. Long-term Context 验收",
        "## 9. Reflection 验收",
        "## 10. Knowledge Base Local 验收",
        "## 11. Google Drive Connector 验收",
        "## 12. Confluence Connector 验收",
        "## 13. Vector Store / Embedding / Rerank 验收",
        "## 14. 汇总判定",
    ]
    for section in required_sections:
        assert section in content


def test_pilot_runbook_contains_required_commands_and_failure_handling():
    content = Path("docs/deployment/pilot-runbook.md").read_text(encoding="utf-8")

    required_phrases = [
        "uv sync --frozen --group dev",
        "uv run python scripts/upgrade.py --dry-run",
        "uv run python scripts/upgrade.py --backup-only",
        "uv run python scripts/upgrade.py",
        "uv run uvicorn fleetent.server:app",
        "curl -fsS http://127.0.0.1:8000/health",
        "uv run fleetent-admin observability traces",
        "uv run fleetent-admin diagnostics export",
        "uv run pytest tests/evaluation/test_memory_extraction_eval.py -q",
        "uv run pytest tests/evaluation/test_long_term_context_eval.py -q",
        "uv run pytest tests/evaluation/test_reflection_report_eval.py -q",
        "uv run fleetent-admin kb connectors check <google_drive_connector_id>",
        "uv run fleetent-admin kb connectors check <confluence_connector_id>",
        "FLEETENT_EVAL_REAL_EMBEDDING=1",
        "失败处理",
        "skipped: credentials not configured",
    ]
    for phrase in required_phrases:
        assert phrase in content
