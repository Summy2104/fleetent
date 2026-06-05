## 1. scaffold 核心（runtime/agent_init.py）

- [x] 1.1 Write failing tests：`tests/unit/test_agent_init.py` —— `scaffold_agent_home("my-bot", home=tmp)` 创建 `tmp/agent.yaml`，其 `name=="my-bot"` 且能被 `agent_config.load_agent_file(tmp)` 加载（目录名==name 校验通过）；`.env` 列出引用的 env 名（含 `ANTHROPIC_API_KEY=`），不含真实密钥；隔离 tmp，不碰真实 ~/.fleetent
- [x] 1.2 Implement：`runtime/agent_init.py` —— 内置模板 + 填 `name`，`AgentFile.model_validate` 自校验，收集 `*_env`/必需 env 名写 `.env`（存在跳过），写 `agent.yaml`，返回 home Path

## 2. 覆盖语义与 home 解析

- [x] 2.1 Write failing tests：已存在 `agent.yaml` 且无 `force` → 抛错/非零、不改原文件；`force=True` → 覆盖 agent.yaml 但保留已存在 `.env`；无 `--home` 时 home==`FLEETENT_HOME/<id>`（复用 `resolve_home`，monkeypatch FLEETENT_HOME 隔离）
- [x] 2.2 Implement：覆盖判断 + `resolve_home` 集成使测试转绿

## 3. CLI 分支（__main__.py: agent init）

- [x] 3.1 Write failing tests：`tests/unit/test_main_cli.py`(新增/扩展) —— `fleetent agent init <id>` 解析 `--home`/`--force`，调用 scaffold；用法字符串含 `agent init`；未知/缺参报错
- [x] 3.2 Implement：`__main__.py` 加 `argv[:2]==["agent","init"]` 分支 + `_parse_agent_init` + next-steps 打印使测试转绿

## 4. 收尾

- [x] 4.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check src tests`；`uv run mypy src` 不新增；`fleetent agent init smoke-x --home <tmp>` 手动 smoke + `agent_config.load_agent_file` 验证
- [ ] 4.2 更新 `__main__.py` 顶部 docstring 用法、CLAUDE.md/README agent 部署段补 `fleetent agent init`；设计文档 `docs/superpowers/specs/2026-06-05-fleetent-agent-init-design.md`（含与平台 materialize 的分工）
