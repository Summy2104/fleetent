## Why

Fleetent 已经转向单 Agent 部署快照：平台数据库负责 authoring，部署时生成每个
Agent 自己的 `agent.yaml`、`.env`、`data/`，runtime 应只依赖当前 Agent home。

但模型配置仍处于旧路径：

- `agent.yaml` 的 `model_overrides` 只能表达 provider/model，无法覆盖 base URL、认证、
  fallback、vision、embedding、rerank 等场景。
- `model/router.py` 仍以 `config/routes.yaml` 和内置 `DEFAULT_ROUTES` 为主。
- 平台 provider 管理当前是全局 provider/route，和 Agent 部署快照没有完整打通。

MVP 尚未上线，本 change 不做旧配置兼容，直接收敛到 Agent-scoped model routing。

## What Changes

- `agent.yaml` 新增必填 `models` 段：`targets` 定义可调用模型端点，`routes`
  定义任务场景到 targets 的 fallback 顺序和参数覆盖。
- `provider` 必填但不枚举，用于展示、审计、计费和平台模板；runtime 由
  `protocol` 决定调用方式。
- `api_key_env` 作为模型凭据 env 字段，默认命名为
  `FLEETENT_MODEL_<TARGET_ID_UPPER>_API_KEY`；不再使用 `ANTHROPIC_API_KEY`
  作为模板默认值。
- LLM、vision、image generation、embedding、rerank 纳入统一 `models.routes`。
- runtime 新增 Agent-scoped model resolver，输出可传输/可缓存的
  `ModelPolicySnapshot`，主路径不再读取 `config/routes.yaml`。
- 平台 materialize 展开 Agent-local `models.targets` 到 `agent.yaml`，并为
  `api_key_env` 生成 `.env` scaffold，保留 operator 已填值。
- 删除旧 `model_overrides` / `routes.yaml` 主路径，不保留兼容 shim。

## Capabilities

### New Capabilities

- `agent-scoped-model-routing`: Agent-local model targets/routes schema、resolver、
  fallback、parameter override、per-Agent credential env contract、service-readable
  model policy snapshot。

### Modified Capabilities

- `agent-definition`: Agent 文件定义从 `model_overrides` 迁移到 `models`。
- `file-agent-runtime`: runtime snapshot 携带并解析 Agent-local `models`。
- `platform-agent-lifecycle`: materialize 写出完整 `models` 和 `.env` scaffold。
- `provider-management`: 平台 provider 管理从 runtime 全局路由依赖降级为 authoring/template
  辅助，不作为 Agent runtime 依赖。

## Module Boundary Impact

- **owning package**: `model` owns model route resolution and provider adapters;
  `runtime` consumes resolved model configs; `platform` materializes authored Agent config.
- **public API surface**: new public resolver types/functions under `fleetent.model`;
  `AgentFile`/`AgentSnapshot` expose `models`; `ModelPolicySnapshot` is the service boundary
  object for agent-loop, memory, knowledge, image, embedding, and rerank consumers.
- **owned tables**: existing `agent_versions` model config field is replaced or reshaped for
  `models`; provider/template storage may be adjusted in `platform` but runtime must not query it.
- **config namespace**: `agent.yaml.models`.
- **cross-module dependencies**: `runtime` and future memory/knowledge services depend on
  `model` public resolver API; `platform.agent_lifecycle` depends on `agent_config.AgentFile`;
  `model` must not import `platform`.
- **migration / shim plan**: no runtime compatibility shim. DB/schema and examples are migrated
  directly because MVP is not live.

## Impact

- **代码**: `agent_config.py`, `runtime/snapshot.py`, `model/router.py` or replacement resolver,
  `runtime/loop.py`, `tools/image_gen_client.py`, `tools/vision_client.py`, intelligence
  embedding/rerank runtime wiring, platform materialize, scaffold/templates/tests.
- **配置**: `config/agent/agent.yaml.example`, local `config/agent.yaml`, local scaffold generated
  by `fleetent agent init`。
- **删除**: `model_overrides` schema usage, production `config/routes.yaml` path,
  `ANTHROPIC_API_KEY` default template naming.
- **分支**: 基于并合回 `main`。
