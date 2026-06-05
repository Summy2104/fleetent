## Why

`agent.yaml`(`AgentFile`)目前只描述了 agent 定义层、智能层、connectors/bindings/access；运行治理(预算、turn 上限、context 压缩、permission gate、provider 熔断)和部署/进程旋钮(sandbox、日志、诊断、session 磁盘、image/vision endpoint)仍只活在全局 `Settings` 里。这是"配置全收口 agent.yaml"三步走的第 1 步:**先扩 schema 收下这些字段**,让单个 agent 能在自己的 `agent.yaml` 里 per-agent 表达全部运行时配置。本步只加字段、不改运行时读取行为(runtime 仍读 `Settings`,字段先就位),把行为切换隔离到阶段 2(`runtime-read-agent-config`),降低风险。

## What Changes

- 在 `AgentFile` 增加运行治理字段组(per-agent 可调):
  - **context 压缩**:`context_max_tokens`、`context_compress_threshold`、`context_keep_recent`、`context_tmax_ratio`、`context_tretained_ratio`、`compression_initial_intent_max`、`context_flap_window`、`context_min_savings_ratio`、`context_min_interval_turns`
  - **分层预算**(`session_*` / `user_*` / `agent_*` 维度):`agent_budget_session_turns/tokens`、`agent_budget_user_turns/tokens`、`agent_budget_agent_turns/tokens`、`agent_budget_user_window`、`agent_budget_agent_window`
  - **loop/budget/guardrail**:`agent_max_turns`、`agent_max_consecutive_failures`、`agent_max_tokens`、`agent_grace_call_token_ratio`、`agent_grace_call_min_tokens`、`agent_loop_repeat_threshold`、`guardrail_repeat_threshold`、`agent_tool_parallel_max`、`loop_detect_ignore_arg_keys`、`sub_agent_timeout_seconds`、`tool_default_timeout_seconds`
  - **permission gate**:`permission_gate_medium_timeout_seconds`、`permission_gate_high_timeout_seconds`
  - **provider 熔断**:`provider_failure_threshold`、`provider_cooldown_seconds`
- 在 `AgentFile` 增加部署/进程字段组(per-agent):
  - `microsandbox_url`、`log_format` / `observability`(logging)、`diagnostics`、session 磁盘(`session_ttl_days`、`session_max_total_mb`、`session_max_count`、`session_cleanup_interval_seconds`)、`image_gen_url/model`、`vision_url/model`、`disabled_skills`、`mcp`(enabled)、`scheduling`、`webhooks`
- **BREAKING(语义,但本步无行为变化)**:`agent_budget_global_*`(global_turns/tokens/window)**不进 `AgentFile`**——分布式独立 agent 进程无处聚合跨 agent 总账,该维度在本收口中砍掉(阶段 3 从 `Settings` 删除)。
- **database_url 不进 `AgentFile`**:由 agent home 推导(`<home>/data/fleetent.db`),yaml 不写绝对路径。
- 治理/部署字段中的密钥仍只走 `*_env` 引用,沿用 `_reject_inline_secrets` 扫描。
- 字段默认值与 `Settings` 当前默认对齐,保证未填写时与现状等价。

## Capabilities

### New Capabilities
<!-- 无新 capability;扩展现有 file-agent-runtime 的 agent.yaml schema -->

### Modified Capabilities
- `file-agent-runtime`: "Self-contained agent config file" requirement 扩展 `agent.yaml` 字段集,纳入 per-agent 运行治理与部署/进程字段组;明确 `agent_budget_global_*` 与 `database_url` 不在该文件中。

## Impact

- 代码:`src/fleetent/agent_config.py`(`AgentFile` schema + `_reject_inline_secrets` 覆盖新增 `*_env` 字段)。
- 复用 `src/fleetent/config.py` 既有子模型(`ObservabilitySettings`、`DiagnosticsSettings`、`McpSettings`、`SchedulingSettings`、`WebhooksSettings`)作为嵌套结构,避免重复定义。
- 无运行时行为变化:runtime 仍读 `Settings`;新增字段先就位、暂不接线(阶段 2 接线)。
- 文档:`config/agent.yaml.example` 增补治理/部署字段示例。
- 测试:`tests/unit` 验证新字段解析、默认值、`*_env` 拒绝内联密钥、`global_*`/`database_url` 不被接受。
