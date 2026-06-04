## 1. config/agent.yaml.example 根模板

- [ ] 1.1 Write failing test：`tests/unit/test_agent_config.py`(扩展) —— `load_agent_home_file(REPO/config/agent.yaml.example)` 加载成功（模板对齐 AgentFile 核心 schema，可被单文件 loader 解析）
- [ ] 1.2 Implement：创建 `config/agent.yaml.example`（单体 home 根模板，核心字段，敏感值 `*_env`，不含 KB/intelligence）使测试转绿

## 2. install.sh seed agent.yaml（扁平 home）

- [ ] 2.1 Write failing tests：`tests/integration/test_install_script.py` —— fresh 安装后 `$FLEETENT_HOME/agent.yaml` 存在（内容来自 agent.yaml.example）、`$FLEETENT_HOME/.env` 存在、**不存在 `$FLEETENT_HOME/config/` 目录**；`agent.yaml` 已存在时不覆盖；`--skip-config` 时不 seed agent.yaml 也不 seed .env
- [ ] 2.2 Implement：重写 `copy_config_templates`——seed `$FLEETENT_HOME/.env` + `$FLEETENT_HOME/agent.yaml`（存在即跳过），不建 config/、不拷贝全局 yaml；使测试转绿

## 3. 收尾

- [ ] 3.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check`；`uv run mypy src` 不新增错误；`bash -n scripts/install.sh`
- [ ] 3.2 更新设计文档 `docs/superpowers/specs/2026-06-04-agent-config-self-contained-design.md` 决策/问题日志（记录：加载器容忍缺失的发现、重排 1→3→2、扁平 home、Dockerfile/init_config 清理留给 drop-global-config-files）；README 一键安装段若提及 config/ 布局则同步为扁平
