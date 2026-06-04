from pathlib import Path


def test_env_example_is_safe_and_local_env_and_secrets_are_ignored():
    env_example = Path(".env.example")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert env_example.exists()
    content = env_example.read_text(encoding="utf-8")
    assert "FLEETENT_AUTO_UPGRADE=false" in content
    assert "ANTHROPIC_API_KEY=" in content
    assert "OPENAI_API_KEY=" in content
    assert "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN=" in content
    assert "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET=" in content
    assert "FLEETENT_CONFLUENCE_USERNAME=" in content
    assert "FLEETENT_CONFLUENCE_TOKEN=" in content
    assert "sk-" not in content
    assert "ma-" not in content
    assert "xoxb-" not in content
    assert "\n.env\n" in f"\n{gitignore}\n"
    assert "\nsecrets/\n" in f"\n{gitignore}\n"


def test_secrets_documentation_describes_flat_untracked_directory():
    content = Path("docs/deployment/secrets.md").read_text(encoding="utf-8")

    required_phrases = [
        "secrets/",
        "平铺",
        "不进 git",
        "confluence-api-token",
        "api_token_env",
        "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
        "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_global_config_example_templates_removed():
    # The deployed agent is self-contained (agent.yaml + .env); the global config
    # files are optional (loaders default when absent) and no longer shipped.
    assert not Path("config/settings.yaml.example").exists()
    assert not Path("config/mcp.yaml.example").exists()
    assert not Path("config/mcp.servers.yaml.example").exists()
    assert Path("config/agent.yaml.example").exists()


def test_dockerfile_includes_deployment_runtime_assets_and_port():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    required_phrases = [
        "COPY scripts/ ./scripts/",
        "COPY config/agent.yaml.example ./config/",
        "COPY .env.example ./",
        'ENTRYPOINT ["./scripts/docker_entrypoint.sh"]',
        "EXPOSE 8765",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_docker_compose_uses_local_env_mounts_and_port():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    required_phrases = [
        "env_file: .env",
        "- ./data:/app/data",
        "- ./config:/app/config",
        "- ./secrets:/app/secrets:ro",
        '"8765:8765"',
        "host.docker.internal:host-gateway",
    ]
    for phrase in required_phrases:
        assert phrase in content
    assert ".env.production" not in content


def test_legacy_mcp_yaml_is_not_tracked_or_required_by_deployment_docs():
    tracked_files = set(Path(".").glob("config/mcp.yaml"))
    deployment_docs = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("docs/deployment").glob("*.md")
    )

    assert not tracked_files
    assert "config/mcp.yaml" not in deployment_docs


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
        "docker compose run --rm fleetent uv run fleetent-admin init-config",
        "docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run",
        "docker compose run --rm fleetent uv run python scripts/upgrade.py",
        "docker compose up -d",
        "curl -fsS http://127.0.0.1:8765/health",
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
        "## 4. SQLite 升级、备份和恢复点",
        "## 5. 启动服务和基础 Health Check",
        "## 6. Observability 和 Diagnostics",
        "## 7. Memory 场景验收",
        "## 8. Long-term Context 场景验收",
        "## 9. Reflection 场景验收",
        "## 10. Knowledge Base Local 场景验收",
        "## 11. Google Drive Connector 场景验收",
        "## 12. Confluence Connector 场景验收",
        "## 13. Vector Store / Embedding / Rerank 场景验收",
        "## 14. 汇总判定",
    ]
    for section in required_sections:
        assert section in content


def test_pilot_runbook_contains_required_commands_and_failure_handling():
    content = Path("docs/deployment/pilot-runbook.md").read_text(encoding="utf-8")

    required_phrases = [
        "自动化测试只能作为辅助证据",
        "验收目标",
        "用户场景",
        "准备数据",
        "应该看到什么",
        "通过标准",
        "失败判断",
        "docker compose run --rm fleetent uv run fleetent-admin init-config",
        "docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run",
        "docker compose run --rm fleetent uv run python scripts/upgrade.py --backup-only",
        "docker compose run --rm fleetent uv run python scripts/upgrade.py",
        "docker compose up -d",
        "curl -fsS http://127.0.0.1:8765/health",
        "uv run fleetent-admin observability traces",
        "uv run fleetent-admin diagnostics export",
        "uv run pytest tests/evaluation/test_memory_extraction_eval.py -q",
        "uv run pytest tests/evaluation/test_long_term_context_eval.py -q",
        "uv run pytest tests/evaluation/test_reflection_report_eval.py -q",
        "uv run fleetent-admin kb connectors check <google_drive_connector_id>",
        "uv run fleetent-admin kb connectors check <confluence_connector_id>",
        "FLEETENT_EVAL_REAL_EMBEDDING=1",
        "skipped: credentials not configured",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_intelligence_roadmap_manual_uses_current_shared_memory_cli():
    content = Path("docs/deployment/intelligence-roadmap-test-manual.md").read_text(
        encoding="utf-8"
    )

    assert "fleetent-admin shared-memory" not in content
    assert "fleetent-admin memory shared" in content


def test_intelligence_roadmap_manual_documents_real_llm_credentials_safely():
    content = Path("docs/deployment/intelligence-roadmap-test-manual.md").read_text(
        encoding="utf-8"
    )

    required_phrases = [
        "FLEETENT_EVAL_REAL_LLM",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "不要写入本手册、验收记录、测试 fixture、commit、issue、日志或 trace",
        "不要记录值",
        "缺少真实 provider key",
        "测试应跳过",
        "需要配置真实 credential 的原因",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_deployment_docs_are_docker_compose_first_and_use_port_8765():
    docs = {
        path: path.read_text(encoding="utf-8")
        for path in [
            Path("docs/deployment/pilot-install-checklist.md"),
            Path("docs/deployment/pilot-acceptance-guide.md"),
            Path("docs/deployment/pilot-runbook.md"),
            Path("docs/capabilities/deployment.md"),
        ]
    }

    for content in docs.values():
        assert "Docker Compose" in content
        assert "8765" in content
        assert "127.0.0.1:8000" not in content
    combined = "\n".join(docs.values())
    assert "Pilot 默认" in combined
    assert "uv run uvicorn fleetent.server:app` 只作为开发模式" in combined
