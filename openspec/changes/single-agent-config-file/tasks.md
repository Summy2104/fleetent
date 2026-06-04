## 1. paths.agent_file() 解析器

- [x] 1.1 Write failing tests：`tests/unit/test_paths.py`(扩展) —— 断言 `paths.agent_file() == base_dir() / "agent.yaml"`；`FLEETENT_HOME` 设置时指向 `$FLEETENT_HOME/agent.yaml`
- [x] 1.2 Implement：`paths.py` 新增 `agent_file()` 使测试转绿

## 2. 单文件 loader（跳过目录名校验）

- [x] 2.1 Write failing tests：`tests/unit/test_agent_config.py`(扩展) —— `load_agent_home_file(path)` 对 home-root `agent.yaml`（name 与目录名无关）加载成功；仍触发 `_reject_inline_secrets`（内联密钥被拒）
- [x] 2.2 Implement：`agent_config.load_agent_home_file()` —— 复用 `AgentFile.model_validate` + `_reject_inline_secrets`，不做目录名校验，使测试转绿

## 3. build_index 单文件优先分支

- [x] 3.1 Write failing tests：`FLEETENT_HOME/agent.yaml` 存在时 `build_index()` 返回单 agent 索引、`default == name`（即便 `bindings.default` false）、不扫描 `config/agents/`；`bindings.channels/users` 进入路由表；home-root 不存在时回退多扫描（既有行为回归保护，含 `bindings.default` 决定 default）
- [x] 3.2 Implement：`build_index` 增加单文件优先分支（存在 `paths.agent_file()` → 单 agent + 强制 default；否则多扫描）使测试转绿

## 4. 消费者集成回归

- [x] 4.1 Write failing tests：`tests/integration` —— 单文件模式下 `scan()`+`current()` 后，snapshot/normalizer 路由能解析到该默认 agent（mock home-root agent.yaml，隔离 FLEETENT_HOME）
- [x] 4.2 Implement：如有必要的小适配使测试转绿（预期消费者无需改；若需则最小改动）

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check src tests`；`uv run mypy src` 不新增错误
- [x] 5.2 写 brainstorming 设计文档 `docs/superpowers/specs/2026-06-04-agent-config-self-contained-design.md`（总体设计 + 决策/问题日志，供最终审核）；CLAUDE.md 数据目录/路径段补「agent home 根 agent.yaml」说明
