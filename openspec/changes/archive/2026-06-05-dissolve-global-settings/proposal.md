## Why

阶段 2(`runtime-read-agent-config`)后,runtime 已全部从当前 agent 配置读取治理/部署/智能层旋钮,
全局 `Settings` 里对应字段成为**无人回读的死代码**。本阶段(三步走第 3 步,收尾)删除这些死字段、
IM tokens 与 `default_agent_name`,把全局 `Settings` 收缩为**平台控制面所需的精简配置**(authoring DB
+ 平台进程日志),并把基于 `Settings` 的部署校验(`config_validation`)改为校验 `agent.yaml`。完成
"配置全收口 agent.yaml":agent 运行时配置只在 agent.yaml,平台只留自己那份精简配置。

## What Changes

- 从 `Settings`(`src/fleetent/config.py`)**删除**已迁移至 agent.yaml 的全部 agent-runtime 字段:
  - 治理:`permission_gate_*`、`context_*`(全套)、`agent_budget_*`(含 global)、`session_*`、
    `agent_max_*`、`sub_agent_timeout_seconds`、`tool_default_timeout_seconds`、`agent_grace_*`、
    `agent_loop_repeat_threshold`、`guardrail_repeat_threshold`、`agent_tool_parallel_max`、
    `loop_detect_ignore_arg_keys`、`provider_failure_threshold`、`provider_cooldown_seconds`
  - 部署:`microsandbox_url`、`image_gen_*`、`vision_*`、`disabled_skills`
  - 智能层/特性字段:`vector_store`、`embedding`、`rerank`、`long_term_ctx`、`knowledge_base`、
    `mcp`、`scheduling`、`webhooks`(这些字段从 `Settings` 移除;**子模型类保留**于中性模块供 `AgentFile` 复用)
- **删除 IM tokens**:`slack_bot_token`、`slack_app_token`、`telegram_bot_token`(IM 走 per-agent
  `connectors`)及其在 `YAML_SECRET_FIELDS` 的条目。
- **删除 `default_agent_name`**:默认 agent 以 `agent.yaml` `bindings.default` 为准。
- **删除 `anthropic_api_key`**:平台不跑 agent loop、不调 LLM,不需要任何 API key;agent 默认路由 key 由
  `model_router` 经 route 的 `api_key_env`(env)解析,属 agent-runtime 侧。删后平台 `Settings` 无任何密钥字段。
- `Settings` 收缩为平台控制面精简配置:仅保留 `database_url`(平台 authoring DB,与 per-agent home DB
  分离)、平台进程日志(`log_format`/`observability`)。
- `config_validation`(`production-config-validation`)从校验 `Settings` 部署字段改为校验 `agent.yaml`
  的治理/部署/智能层字段与 inline-secret。
- **BREAKING**:`config/settings.yaml` 不再承载 agent-runtime namespace;旧部署需把这些字段迁到对应
  agent 的 `agent.yaml`。`default_agent_name`、IM tokens 从 `settings.yaml`/env 的 `Settings` 侧移除。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `configuration`: 收缩"Minimal settings surface"为平台控制面精简集;移除 agent-runtime namespace
  (intelligence/scheduling/webhooks/mcp/diagnostics)与 KB connector 配置(迁至 agent.yaml);secrets
  surface 移除 IM tokens。
- `default-agent`: 移除 `Settings.default_agent_name`,默认 agent 解析以 `bindings.default` 为唯一来源;
  CLI set/unset-default 作用于 agent.yaml 而非 `settings.yaml`。
- `production-config-validation`: 部署校验对象从 `Settings` 字段改为 `agent.yaml`。

## Impact

- 代码:`src/fleetent/config.py`(删字段、收缩 `Settings`、子模型类迁中性模块)、`platform/config_validation.py`
  (retarget agent.yaml)、所有阶段 2 已切换来源的模块(确认不再 import 被删字段)。
- 平台 stores 继续用 `Settings().database_url`(平台 authoring DB),不受影响。
- 文档:`config/settings.yaml.example` 收缩为平台精简示例;`config/agent.yaml.example` 已含 agent-runtime
  字段(阶段 1)。
- 测试:`Settings` 不再含被删字段(断言移除);`config_validation` 对 agent.yaml 生效;默认 agent 走
  `bindings.default`;IM tokens 不再被 `Settings` 接受。
- 依赖前置:必须在阶段 2 合并后执行,否则删字段会破坏仍在回读的 runtime。
