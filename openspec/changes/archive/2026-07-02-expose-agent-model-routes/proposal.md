## Why

Agent 的模型路由后端已支持 9 个标准路由键（`fleetent.model.resolver.STANDARD_ROUTE_KEYS`）：
`default` / `memory_extraction` / `kb_extraction` / `vision` / `embedding` / `rerank` /
`image_generation` / `audio_transcription` / `audio_generation`，`agent.example.yaml` 也完整
示范了 `models.routes`。

但管理控制台的 Agent 配置页（`frontend/src/features/agents/configure.tsx` 的 `ROUTE_BINDINGS`）
只暴露了其中 4 个：`default` / `embedding` / `memory_extraction` / `image_generation`。运维在 UI
上无法为 `vision` / `kb_extraction` / `rerank` / `audio_transcription` / `audio_generation`
选择模型，只能改回手写 `agent.yaml` 或走 Advanced overrides 文本框，与「控制台即 authoring 入口」
的产品意图不符。

后端接口无需新增字段：`model_overrides` 已是 free-form `dict[str, Any]`（update/create body），
`platform.agent_lifecycle.materialize._models_from_overrides` 按任意 route key 逐路由合并到 baseline，
并从 model 记录的 `protocol` 分派调用方式。因此本 change 主体是前端把缺失的 5 个路由补齐为
可选项，后端只做「新路由键能端到端 round-trip」的验证，不改 API 契约。

## What Changes

- 前端 `ROUTE_BINDINGS` 补齐 5 个缺失路由：`vision`、`kb_extraction`、`rerank`、
  `audio_transcription`、`audio_generation`，每个路由声明其候选模型的 `protocol` 过滤集。
- 模型路由从 overview tab 拆到**独立的 Models tab**（9 个选择器 + provider key override 自成一页），
  overview tab 只保留 name / system_prompt / allowed_tools / memory_namespace / YAML 导出；
  两个 tab 各自独立 save（overview 存前四项，Models 存 `model_overrides` + provider key secret）。
- 为新增路由添加 i18n label / hint（中英双语），沿用现有 `agents.model*` 键命名风格。
- 音频两个路由（`audio_transcription` / `audio_generation`）为保留路由：当前无对应 provider
  protocol，UI 显式呈现选择器但候选列表为空，并给出「暂无支持该协议的模型」提示，避免误导。
- 后端验证（非契约变更）：新增 integration 测试证明新路由键经现有 `PATCH /admin/agents/{name}`
  的 `model_overrides` 正确 round-trip 进 `agent.yaml` 的 `models.routes`。

## Capabilities

### Modified Capabilities

- `agent-admin-ui`: Agent 配置页的模型路由选择器从 4 个扩展到覆盖全部 `STANDARD_ROUTE_KEYS`，
  按路由 protocol 过滤候选模型，保留路由在无候选时给出明确提示。

## Module Boundary Impact

- **owning package**: `frontend`（`features/agents` UI）owns the route-binding surface;
  `platform.agent_management_console` / `platform.agent_lifecycle` 保持现状消费 `model_overrides`。
- **public API surface**: 无新增。复用现有 `PATCH /admin/agents/{name}` 的 `model_overrides`
  字段与 `GET` 回读的 `model_overrides`；前端复用 `withRouteModel` / `routeModelId` 帮助函数。
- **owned tables**: 无。`model_overrides` 落 `agent_versions`，本 change 不改 schema。
- **config namespace**: `agent.yaml.models.routes`（已存在，不新增命名空间）。
- **cross-module dependencies**: 前端依赖 `/admin/models` 返回带 `protocol` 的模型列表以过滤候选；
  无新增跨模块后端依赖。`agent` 运行时解耦不受影响（纯 authoring/UI 改动）。
- **migration / shim plan**: 无 schema / 迁移。旧 `agent.yaml` 未配置这些路由时，resolver 仍回落
  baseline 默认目标，行为不变；无兼容 shim 需要。
