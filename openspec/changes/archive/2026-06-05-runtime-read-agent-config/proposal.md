## Why

阶段 1(`agent-yaml-governance-schema`)让 `AgentFile` 能承载治理/部署字段,但 runtime 仍从全局
`Settings` 读取——agent.yaml 里的这些字段(以及早先就加进 schema 的智能层字段)目前**解析了却空转**。
本阶段把 runtime / intelligence / session / skills / tools 各处的 `Settings()` 读取切换到读**当前 agent
的配置**,让 per-agent 配置真正生效。这是"配置全收口"三步走的第 2 步,也是风险最高的一步(`Settings()`
散见于 14 文件 21 处)。

## What Changes

- 在 `AgentSnapshot`(`runtime/snapshot.py`)上扩展携带**per-run/per-request 治理配置**:context 压缩、
  分层预算(session/user/agent 维度)、loop/budget/guardrail、permission gate、provider 熔断、
  `tool_default_timeout_seconds`、`sub_agent_timeout_seconds`。`_snapshot_from_file` 从 `AgentFile`
  填充;`_snapshot`(DB 授权侧)用 `Settings` 默认填充以保持兼容。
- 把 `runtime/loop.py` 的 `_resolve_budget_config` / `_resolve_loop_config` / `_resolve_guardrail_threshold`
  / `_resolve_parallel_max` / `_resolve_default_tool_timeout`,以及 `budget.py` / `context.py` /
  `layered_budget.py` / `termination.py` / `sub_agent_lifecycle.py` 的 `Settings()` 回退,改为从传入的
  snapshot / agent config 解析;保持 `call-param > agent config > default` 优先级。
- 智能层(`intelligence/vector_store/*`、`knowledge_base/*`、`long_term_ctx*`、`memory/store`、
  `reflection`)从读全局 `Settings` 的智能层子配置切换到读当前 agent 的对应字段(消除空转)。
- **进程级部署旋钮**(session 磁盘清理间隔、`disabled_skills`、日志/observability、`microsandbox_url`、
  image/vision endpoint、diagnostics)在 standalone agent 进程**启动时从当前(单)agent 解析一次**:
  `session/manager.py`、`skills/registry.py`、`tools/image_gen_client.py`、`tools/vision_client.py`、
  `observability/diagnostics.py`、`model/provider_health.py`。
- 删除 `agent_budget_global_*` 的运行时读取路径(global 维度已在阶段 1 排除出 schema)。
- 行为等价保证:当 agent.yaml 未填某字段时,解析结果等于该字段当前 `Settings` 默认,现状行为不变。

## Capabilities

### New Capabilities
- `agent-scoped-runtime-config`: runtime 治理与部署旋钮的解析契约——per-run 治理随 `AgentSnapshot`(每
  请求解析的 agent)走;进程级部署旋钮在 agent 进程启动时从当前 agent 解析;优先级 call-param > agent
  config > 字段默认;`Settings` 仅作为尚未迁移字段的过渡来源(阶段 3 移除)。

### Modified Capabilities
- `agent-iteration-budget`: 迭代/turn 上限的配置来源从全局 `Settings` 改为当前 agent 配置(per-agent)。
- `agent-cost-budget`: 分层预算(session/user/agent)来源改为当前 agent 配置;移除 global 维度的读取。
- `tool-timeout`: 默认工具超时来源改为当前 agent 配置。

(智能层 [vector_store/embedding/rerank/kb/long_term_ctx] 的来源切换由新 capability `agent-scoped-runtime-config`
的 "Intelligence layer reads the active agent's configuration" requirement 统一承载,不单独改 `long-term-ctx` spec。)

## Impact

- 代码:`runtime/{snapshot,loop,budget,context,layered_budget,termination,sub_agent_lifecycle}.py`、
  `intelligence/**`、`session/manager.py`、`skills/registry.py`、`tools/{image_gen_client,vision_client}.py`、
  `observability/diagnostics.py`、`model/provider_health.py`。
- `Settings` 本身**不删**(阶段 3),本阶段仅切换读取来源;切换后这些字段在 `Settings` 成为死代码,阶段 3 清除。
- 多 agent(dev/平台)态:per-run 治理随 per-request snapshot,天然支持不同 agent 不同配置;进程级旋钮在
  多 agent 共享进程时取默认(平台已不跑 agent loop,此态仅 dev,影响可控)。
- 测试:per-agent 配置生效、未填字段等价旧默认、global 维度读取路径消失、智能层不再读全局 Settings。
