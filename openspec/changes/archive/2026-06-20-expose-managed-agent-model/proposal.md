## Why

实测拉通 managed 栈(platform → node → agent)时发现:**控制面没有任何 API 能给 managed agent 配模型**。apply API 的 `AgentSpec` 只收 `name`/`system_prompt`/`allowed_tools`,`/admin/agents/{name}/agent-yaml` 是只读导出,没有端点写 `model_overrides`。结果 materialize 走 `_models_from_overrides(agent.model_overrides)`,overrides 为空就回落到 `default_models()` —— 产出占位模型 `"default"`,运行时 404。

也就是说:**platform 创建、node 拉起的 agent 跑不了真实模型,完整 managed 对话链路无法闭环**。`agent_store.create_version` 其实早已接受 `model_overrides` 参数,缺的只是把它暴露到控制面 API。

## What Changes

- apply API 的 agent 定义补上**可选的模型配置**字段:`AgentSpec` 增加 `model_overrides`(沿用 `{routes: {route_key: [target entries]}}` 形状,镜像 agent.yaml 的 `models` 段),贯穿到 `create_agent_def` → `agent_store.create_version(model_overrides=...)`。
- materialize 在 `agent.model_overrides` 非空时产出真实模型策略(现状已支持);本 change 保证 overrides **能被写进去**,从而 materialize 不再回落到 `default_models()` 占位。
- 模型所需的 API key 仍走**已有**的 `/admin/agents/{name}/secrets` + desired-state 注入路径(node 注入 `api_key_env`),本 change 不动密钥面。
- 不传 `model_overrides` 时行为不变(回落 `default_models()`),**非破坏性**、幂等语义保留。

## Capabilities

### New Capabilities
<!-- 无新增独立 capability;模型配置属既有 agent 定义面的扩展 -->

### Modified Capabilities
- `fleetent-apply-api`: agent 定义新增可选 `model_overrides` 字段(apply 拥有的"定义面"从 `system_prompt`/`allowed_tools`/`model` 扩展到包含模型路由策略);幂等与"不碰 bindings"语义不变。
- `agent-admin-api`:(若 design 决定加专用端点)managed agent 模型配置的读写端点;否则仅复用 apply 路径,本条留空。

## Impact

- `src/fleetent/platform/askit_console/agent_apply_api.py` — `AgentSpec` 增字段、`create_agent_def` 透传。
- `src/fleetent/platform/agent_lifecycle/materialize.py` — 不改逻辑,验证 overrides 非空时产出真实模型(回归保护)。
- `src/fleetent/agent_store.py` — `create_version` 已接受 `model_overrides`,无改动(仅被新路径调用)。
- 测试:apply 带 `model_overrides` → `agent_versions.model_overrides` 落库 → materialize 产出真实模型(非 `"default"`)的集成验证。
- 文档:apply API 字段说明同步。
