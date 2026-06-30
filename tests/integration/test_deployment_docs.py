from pathlib import Path

import yaml


def _walk(node: object):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _env_refs_from_yaml(path: Path) -> set[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    refs: set[str] = set()
    for key, value in _walk(doc):
        if isinstance(value, str) and key.endswith("_env") and value:
            refs.add(value)
    return refs


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_is_safe_and_local_env_and_secrets_are_ignored():
    agent_env = Path("agent.env.example")
    platform_env = Path(".env.example")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert agent_env.exists() and platform_env.exists()
    agent = agent_env.read_text(encoding="utf-8")
    platform = platform_env.read_text(encoding="utf-8")
    both = agent + "\n" + platform

    # Platform-side
    for key in ("FLEETENT_SECRET_KEY", "DATABASE_URL", "LOG_FORMAT"):
        assert f"{key}=" in platform
        assert f"{key}=\n" in platform
    assert "FLEETENT_MODEL_PRIMARY_API_KEY=" not in platform
    # Agent-side
    assert "FLEETENT_SECRET_KEY=" not in agent
    assert "DATABASE_URL=" not in agent
    assert "LOG_FORMAT=" not in agent
    assert "MICROSANDBOX_URL=" not in agent
    assert "ANTHROPIC_API_KEY=" not in agent
    assert "OPENAI_API_KEY=" not in agent
    assert "FLEETENT_MODEL_PRIMARY_API_KEY=" in agent
    assert "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN=" not in agent
    assert "FLEETENT_CONFLUENCE_TOKEN=" not in agent
    assert "materialize" in agent
    # No real secret material in either.
    for marker in ("sk-", "ma-", "xoxb-", "xapp-"):
        assert marker not in both
    assert "\n.env\n" in f"\n{gitignore}\n"
    assert "\nsecrets/\n" in f"\n{gitignore}\n"


def test_secrets_documentation_describes_flat_untracked_directory():
    content = Path("docs/operations/secrets.md").read_text(encoding="utf-8")

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
    # Examples live beside their runtime instance paths in Platform/Agent homes.
    assert not Path("config/settings.yaml.example").exists()
    assert not Path("config/mcp.yaml.example").exists()
    assert not Path("config/mcp.servers.yaml.example").exists()
    assert not Path("config/agent.yaml.example").exists()
    assert not Path("config/agent.yaml").exists()
    assert not Path("config/knowledge.yaml.example").exists()
    assert Path(".env.example").exists()
    assert Path("platform.yaml.example").exists()
    assert Path("agent.yaml.example").exists()
    assert Path("agent.env.example").exists()
    assert not Path("agents/default").exists()
    assert not Path("agent.env.standalone.example").exists()
    assert not Path("agent.configure.yaml.example").exists()
    assert not Path("agent.defaults.yaml.example").exists()
    assert not Path("config").exists()
    assert not Path("config/agent").exists()
    assert not Path("config/platform").exists()
    assert not Path("config/knowledge-service").exists()
    assert not Path("config/agents").exists()
    assert not Path("examples/knowledge-service").exists()


def test_config_directory_is_not_a_runtime_or_template_namespace():
    assert not Path("config").exists()


def test_active_docs_and_source_do_not_reintroduce_legacy_config_paths():
    forbidden = [
        "config/mcp.servers.yaml",
        "config/settings.yaml",
        "config/agent/",
        "config/platform/",
        "config/agents",
        "FLEETENT_HOME/<id>",
        "FLEETENT_HOME/<agent-id>",
        "FLEETENT_HOME/agent.yaml",
        ".env.standalone.example",
        "agent.configure.yaml.example",
        "agent.defaults.yaml.example",
    ]
    roots = [Path("README.md"), Path("docs/capabilities"), Path("docs/operations"), Path("src")]
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix not in {".md", ".py", ".sh", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                if needle in text:
                    offenders.append(f"{path}: {needle}")
    assert not offenders


def test_four_canonical_examples_are_complete_references():
    from fleetent.agent_config import AgentFile
    from fleetent.knowledge_base.config import load_knowledge_config

    agent_yaml = Path("agent.yaml.example")
    agent_env = Path("agent.env.example")
    platform_yaml = Path("platform.yaml.example")
    platform_env = Path(".env.example")

    agent = AgentFile.model_validate(yaml.safe_load(agent_yaml.read_text(encoding="utf-8")))
    agent_fields = set(AgentFile.model_fields)
    example_fields = set((yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}).keys())
    # The example uses the standard external `mcpServers` map key; the before-validator
    # maps it onto the internal `mcp_servers` field, so it documents that field.
    if "mcpServers" in example_fields:
        example_fields.add("mcp_servers")
    assert agent.name
    assert not (agent_fields - example_fields)

    missing_agent_env = _env_refs_from_yaml(agent_yaml) - _env_keys(agent_env)
    assert not missing_agent_env
    assert ".env.standalone.example" not in agent_env.read_text(encoding="utf-8")

    missing_platform_env = _env_refs_from_yaml(platform_yaml) - _env_keys(platform_env)
    assert not missing_platform_env
    assert {"FLEETENT_SECRET_KEY", "DATABASE_URL"} <= _env_keys(platform_env)
    load_knowledge_config(platform_yaml)


def test_dockerfile_includes_deployment_runtime_assets_and_port():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    required_phrases = [
        "FROM docker:27-cli AS docker-cli",
        "COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker",
        "COPY scripts/ ./scripts/",
        "COPY platform.yaml.example .env.example agent.yaml.example agent.env.example ./",
        'ENV PATH="/app/.venv/bin:$PATH"',
        'ENV PYTHONPATH="/app:/app/src:$PYTHONPATH"',
        "ARG GIT_COMMIT=unknown",
        "ENV FLEETENT_BUILD_COMMIT=$GIT_COMMIT",
        'LABEL org.opencontainers.image.revision="$GIT_COMMIT"',
        'ENTRYPOINT ["./scripts/docker_entrypoint.sh"]',
        "EXPOSE 8765",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_docker_compose_runs_managed_stack_with_path_parity_and_socket_boundary():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    required_phrases = [
        "platform:",
        "node:",
        "kb-worker:",
        "kb-serve:",
        'command: ["platform"]',
        'command: ["node"]',
        (
            'command: ["kb-worker", "--config", '
            '"${FLEETENT_HOME:?set FLEETENT_HOME}/kb-service/default/kb-service.yaml"]'
        ),
        (
            'command: ["kb-serve", "--config", '
            '"${FLEETENT_HOME:?set FLEETENT_HOME}/kb-service/default/kb-service.yaml"]'
        ),
        "- ${FLEETENT_HOME:?set FLEETENT_HOME}/kb-service/default/.env",
        '"8765:8765"',
        '"8767:8767"',
        "FLEETENT_AUTO_UPGRADE: ${FLEETENT_AUTO_UPGRADE:-false}",
        "FLEETENT_NODE_BACKEND: container",
        "FLEETENT_NODE_AGENT_NETWORK: fleetent",
        "/var/run/docker.sock:/var/run/docker.sock",
        "${FLEETENT_HOME:?set FLEETENT_HOME}:${FLEETENT_HOME:?set FLEETENT_HOME}",
        "name: fleetent",
    ]
    for phrase in required_phrases:
        assert phrase in content
    assert content.count("/var/run/docker.sock:/var/run/docker.sock") == 1
    auto_upgrade_lines = [
        line for line in content.splitlines() if line.lstrip().startswith("FLEETENT_AUTO_UPGRADE:")
    ]
    assert len(auto_upgrade_lines) == 1
    assert "./data:/app/data" not in content


def test_legacy_mcp_yaml_is_not_tracked_or_required_by_deployment_docs():
    tracked_files = set(Path(".").glob("config/mcp.yaml"))
    deployment_docs = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("docs/operations").glob("*.md")
    )

    assert not tracked_files
    assert "config/mcp.yaml" not in deployment_docs


def test_pilot_install_checklist_exists_and_covers_required_sections():
    checklist = Path("docs/operations/pilot-install-checklist.md")

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
    content = Path("docs/operations/pilot-install-checklist.md").read_text(encoding="utf-8")

    required_commands = [
        "docker compose run --rm fleetent uv run fleetent platform init-config",
        "docker compose run --rm fleetent uv run fleetent platform upgrade --dry-run",
        "docker compose run --rm fleetent uv run fleetent platform upgrade",
        "docker compose up -d",
        "curl -fsS http://127.0.0.1:8765/health",
        "平台托管 KB ingest 已退役",
        "kb-service.yaml",
        "kb-worker --config $FLEETENT_HOME/kb-service/default/kb-service.yaml",
        "GET /admin/stats/agents/<agent_id>/overview",
        "GET /admin/stats/agents/<agent_id>/tools",
        "GET /admin/stats/sessions/<session_id>/trace",
        "uv run fleetent platform diagnostics export",
        "uv run fleetent platform diagnostics retention dry-run",
    ]
    for command in required_commands:
        assert command in content


def test_pilot_install_checklist_documents_secret_and_reporting_boundaries():
    content = Path("docs/operations/pilot-install-checklist.md").read_text(encoding="utf-8")

    required_phrases = [
        "不要把真实 secret、token、credential payload 写入 agent config、日志、trace",
        "diagnostics package、issue 或测试 fixture",
        "`*_env` 引用",
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
    runbook = Path("docs/operations/pilot-runbook.md")

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
    content = Path("docs/operations/pilot-runbook.md").read_text(encoding="utf-8")

    required_phrases = [
        "自动化测试只能作为辅助证据",
        "验收目标",
        "用户场景",
        "准备数据",
        "应该看到什么",
        "通过标准",
        "失败判断",
        "docker compose run --rm fleetent uv run fleetent platform init-config",
        "docker compose run --rm fleetent uv run fleetent platform upgrade --dry-run",
        "docker compose run --rm fleetent uv run fleetent platform upgrade --backup-only",
        "docker compose run --rm fleetent uv run fleetent platform upgrade",
        "docker compose up -d",
        "curl -fsS http://127.0.0.1:8765/health",
        "GET /admin/stats/agents/<agent_id>/overview",
        "uv run fleetent platform diagnostics export",
        "uv run pytest tests/evaluation/test_memory_extraction_eval.py -q",
        "uv run pytest tests/evaluation/test_long_term_context_eval.py -q",
        "uv run pytest tests/evaluation/test_reflection_report_eval.py -q",
        "平台托管 KB ingest 已退役",
        "kb-service.yaml",
        "kb-worker --config $FLEETENT_HOME/kb-service/default/kb-service.yaml",
        "FLEETENT_EVAL_REAL_EMBEDDING=1",
        "skipped: credentials not configured",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_intelligence_roadmap_manual_references_agent_memory_governance_flow():
    content = Path("docs/roadmaps/intelligence-roadmap-test-manual.md").read_text(encoding="utf-8")

    assert "fleetent-admin shared-memory" not in content
    assert "fleetent-admin" not in content
    assert "fleetent-node" not in content
    assert "fleetent admin memory shared" not in content
    # The rescope renamed Shared Memory → Agent Memory; the manual now drives the
    # governance flow through the agent-memory write-path integration test.
    assert "Agent Memory apply / reject" in content
    assert "tests/integration/test_agent_memory_write_path.py" in content


def test_intelligence_roadmap_manual_documents_real_llm_credentials_safely():
    content = Path("docs/roadmaps/intelligence-roadmap-test-manual.md").read_text(encoding="utf-8")

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
            Path("docs/operations/pilot-install-checklist.md"),
            Path("docs/operations/pilot-acceptance-guide.md"),
            Path("docs/operations/pilot-runbook.md"),
        ]
    }

    for content in docs.values():
        assert "Docker Compose" in content
        assert "8765" in content
        assert "127.0.0.1:8000" not in content
    combined = "\n".join(docs.values())
    assert "Pilot 默认" in combined
    assert "uv run uvicorn fleetent.server:app` 只作为开发模式" in combined


def test_compose_deployment_runbook_documents_operations_and_boundaries():
    runbook = Path("docs/deployment/compose.md")

    assert runbook.exists()
    content = runbook.read_text(encoding="utf-8")

    required_phrases = [
        "Docker Compose 推荐生产路径",
        "make up",
        "make redeploy",
        "make deploy-status",
        "make upgrade",
        "make down",
        "path-parity",
        "DEPLOY_FLEETENT_HOME",
        "FLEETENT_HOME",
        "docker.sock 信任边界",
        "rootless Docker",
        "platform / node / kb-worker / kb-serve",
        "node.backend=container",
        "agent 兄弟容器",
        "build commit",
        "陈旧",
        "回滚",
        "不带 -v",
    ]
    for phrase in required_phrases:
        assert phrase in content


def test_readme_points_production_deployments_to_compose_runbook():
    content = Path("README.md").read_text(encoding="utf-8")

    assert "Docker Compose 推荐生产路径" in content
    assert "docs/deployment/compose.md" in content
    assert "node.backend=process" in content


def test_materialize_covers_agent_yaml_example_env_refs(tmp_path, monkeypatch):
    """Every env-var name referenced by agent.yaml.example is generated into Agent .env."""
    import yaml

    from fleetent.agent_config import AgentFile
    from fleetent.platform.agent_lifecycle import materialize

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    doc = yaml.safe_load(Path("agent.yaml.example").read_text(encoding="utf-8"))

    refs: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key.endswith("_env"):
                    refs.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    agent = AgentFile.model_validate(doc)
    home = materialize.write_home(agent)
    env_text = (home / ".env").read_text(encoding="utf-8")
    missing = sorted(name for name in refs if name and f"{name}=" not in env_text)
    assert not missing, f"materialized .env missing referenced env names: {missing}"


def test_deployment_docs_do_not_use_old_agent_config_paths_as_primary():
    docs = {
        path: path.read_text(encoding="utf-8")
        for path in [
            Path("README.md"),
            Path("docs/operations/pilot-install-checklist.md"),
            Path("docs/operations/pilot-acceptance-guide.md"),
            Path("docs/operations/pilot-runbook.md"),
        ]
    }

    combined = "\n".join(docs.values())
    assert "config/agent.yaml.example" not in combined
    assert "cp config/agent.yaml.example config/agent.yaml" not in combined
    assert "config/agent.yaml`" not in combined
    assert "FLEETENT_HOME/agent.yaml" not in combined
    assert "agents/<agent-id>/agent.yaml" in combined
