## Context

managed agent 的模型策略来源于 `agent_versions.model_overrides`:materialize 的 `_models_from_overrides(agent.model_overrides)` 把它展开成运行时 `AgentModels`(`targets` + `routes`);overrides 为空则回落 `default_models()`,产出占位模型 `"default"`(运行时 404)。

`model_overrides` 形状(由 `_models_from_overrides` + `_target_from_model_override` 反推):
```
{ "routes": { "<route_key>": [ {provider, model, base_url, api_key_env, protocol?, max_tokens?, params?}, ... ] } }
```
镜像 agent.yaml 的 `models` 段(routes → targets)。`agent_store.create_version(name, ..., model_overrides=_UNSET, ...)` 已接受该参数并落库。

缺口:**没有控制面 API 把 `model_overrides` 写进 agent 定义**。
- apply (`POST /admin/agents/apply`):`AgentSpec` = name/system_prompt/allowed_tools,`create_agent_def` 不透传 model。
- `/admin/agents/{name}/agent-yaml`:GET 只读导出。
- 密钥(`api_key_env` 的值)走已有 `/admin/agents/{name}/secrets` + desired-state 注入,**不在本 change**。

## Goals / Non-Goals

**Goals:**
- 控制面能给 managed agent 写模型路由策略(`model_overrides`),让 materialize 产出真实模型而非 `default_models()` 占位。
- 复用 apply 这条"agent 定义"入口,保持幂等 + "不碰 bindings"语义。
- 不传 model 时行为零变化(回落 `default_models()`),非破坏性。

**Non-Goals:**
- 不动密钥面(`api_key_env` 值仍走 `/secrets` + desired-state)。
- 不改 materialize 解析逻辑(只验证非空 overrides 产出真实模型)。
- 不做 model 配置的 schema 校验/provider 健康探测(沿用运行时既有路径)。
- 不引入新 UI(console picker 已有自己的 overrides 写入路径,不在本 change)。

## Decisions

**D1 — 走 apply 扩展,而非新增专用端点。** 模型策略属"agent 定义"的一部分(与 system_prompt/allowed_tools 同级),apply 的既有要求「Apply owns the agent definition」已声明定义面含 `model`。`AgentSpec` 增加可选 `model_overrides: dict | None`,`create_agent_def(name, system_prompt, allowed_tools, model_overrides=None)` 透传到 `agent_store.create_version(model_overrides=...)`。`None`/缺省时不写(保留 `_UNSET` 语义),行为不变。`agent-admin-api` 不加专用端点(proposal 的可选项放弃),减少面。

**D2 — overrides 形状原样沿用 materialize 约定。** API 不重新定义结构,直接收 `{routes: {...}}` 透传给 `create_version`,由 materialize 既有解析消费。API 层不做深度校验(避免与运行时解析重复/漂移),非法结构在 materialize 回落 `default_models()` —— 与现状一致,不是本 change 退化。

**D3 — 密钥分离。** `model_overrides` 只存 `api_key_env`(环境变量名,非密钥值)。真实 key 经 `/admin/agents/{name}/secrets` 写入、node 按 desired-state 注入环境。本 change 不碰密钥,文档明确两者协同。

**D4 — 幂等保持。** 同一 spec(含相同 `model_overrides`)重复 apply 产出相同状态;`model_overrides` 进入 version 快照,re-apply 不产生额外副作用(除 audit/version 时间戳)。

### 模块边界影响(AGENTS.md 要求)

- **owning package**:`platform`(`askit_console/agent_apply_api.py`)。
- **public API surface**:`AgentSpec.model_overrides`(新可选字段);`create_agent_def(..., model_overrides=None)` 签名扩展。
- **owned tables**:无新增。复用 `agent_versions.model_overrides`(既有列)。
- **config namespace**:无新增。
- **cross-module dependencies**:`platform` → `agent_store.create_version`(既有 public API,无新依赖);materialize 既有消费,方向不变。无反向依赖(agent runtime 不 import platform)。
- **migration / shim plan**:无 schema 迁移;无模块移动;无 shim。

## Risks / Trade-offs

- **API 不校验 overrides 结构**(D2):非法结构静默回落 `default_models()`,与显式报错相比可观测性弱。权衡:不在 API 与运行时之间复制校验逻辑(漂移风险更高);回落行为本就是现状。后续若需要,可在 materialize 加结构告警(本 change 不做)。
- **密钥与模型分两个端点**(D3):配 managed agent 需两步(apply 配 model + secrets 配 key)。权衡:密钥面已独立设计(desired-state 注入),合并会破坏既有边界。文档需写清协同顺序。
- **console picker 与 apply 两条写入路径**:`_models_from_overrides` 注释提到 console 的 two-part picker 也写 overrides。两条路径写同一列,形状一致(均 `{routes:...}`),无冲突;本 change 不统一二者。
