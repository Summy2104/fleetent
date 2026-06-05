## 1. 治理字段组(context 压缩 / 分层预算 / loop·guardrail / permission gate / provider 熔断)

- [x] 1.1 Write failing tests for governance fields: `tests/unit/test_agent_config.py` 断言 `agent.yaml`
      声明 `agent_max_turns: 30`、`context_compress_threshold: 0.7` 等可解析;断言全部省略时默认值等于
      `Settings` 默认(`agent_max_turns==50`、`tool_default_timeout_seconds==30.0` 等);断言两个 agent 各
      自携带独立值。运行 `uv run pytest tests/unit/test_agent_config.py -x -q` 必须见红
- [x] 1.2 在 `AgentFile`(`src/fleetent/agent_config.py`)平铺加入 context 压缩 + 分层预算(session/user/
      agent 维度,不含 global)+ loop/budget/guardrail + permission gate + provider 熔断字段,默认值逐项
      对齐 `Settings`(config.py:200-265)。运行测试见绿

## 2. 部署/进程字段组

- [x] 2.1 Write failing tests for deployment fields: 断言 `microsandbox_url`、`session_ttl_days` 等标量
      字段可解析;断言 `observability.logging.console_level: debug` 解析为 `ObservabilitySettings`;断言
      `diagnostics`/`mcp`/`scheduling`/`webhooks` 嵌套块解析为对应复用子模型。运行见红
- [x] 2.2 在 `AgentFile` 加入部署字段:标量(`microsandbox_url`/`log_format`/`image_gen_*`/`vision_*`/
      session 磁盘四项/`disabled_skills`)平铺;`observability`/`diagnostics`/`mcp`/`scheduling`/`webhooks`
      复用 `config.py` 既有子模型(import,不重定义)。运行见绿

## 3. 排除项:global 预算 + database_url

- [x] 3.1 Write failing tests: 断言 `agent.yaml` 写 `agent_budget_global_tokens` 或 `database_url` 时
      因 `extra="forbid"` fail fast,错误指明未知字段。运行见红(若已默认拒绝则补断言锁定行为)
- [x] 3.2 确认 `AgentFile.model_config` 的 `extra="forbid"` 覆盖这些字段(不新增字段即拒绝);如需更友好
      的错误信息可加 validator。运行见绿

## 4. 内联密钥扫描覆盖

- [x] 4.1 Write failing test: 在部署/治理 payload 里塞一个内联 secret 形态的 `*_env` 位置值,断言
      `_reject_inline_secrets` fail fast 且错误含 agent 名/字段/文件。运行见红
- [x] 4.2 扩展 `_reject_inline_secrets`,把新增部署 payload 并入按 `_is_secret_reference_key` 过滤的扫描。
      运行见绿

## 5. 文档与收尾

- [x] 5.1 在 `config/agent.yaml.example` 增补治理 + 部署字段示例,注释标注"本阶段字段已就位但 runtime
      暂未接线,行为以全局 Settings 为准"
- [x] 5.2 `uv run ruff format src tests && uv run ruff check src tests` + `uv run mypy src` 通过
- [x] 5.3 全量 `uv run pytest -x -q` 与 `uv run python scripts/check_test_layers.py` 通过
