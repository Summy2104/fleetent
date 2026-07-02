## Why

运行时的模型路由本就按「场景 route → 有序 target 链」消费：`resolve(route_key)` 返回有序
fallback 链，`call_with_policy` 遇 `ModelCallSwitchableError` 逐个降级（`model/resolver.py`）。
`agent.example.yaml` 也示范了 `default: [primary, backup]` 这种 fallback + per-route 参数覆盖。

但控制台的模型选择器（`expose-agent-model-routes` 引入的 Models tab）只能给每个 route 选**单个**
模型，写出单元素链——运行时拿到的就是无 fallback 的单目标。要配 fallback / per-route
temperature，运维只能手写 `agent.yaml` 或走 Advanced overrides 文本框，与「控制台即 authoring
入口」不符。

后端**无需改动**：`model_overrides.routes.<key>` 已接受 entry 列表，`_models_from_overrides`
（`materialize.py`）逐 entry 构建 `ModelRouteEntry`（含 `max_tokens` / `params`），named-target
复用经 model id 自动去重。差距纯在 UI——它只写单 entry。本 change 把 Models tab 的每个 route
从「单选」升级为「有序 fallback 链 + per-entry temperature/max_tokens 覆盖」。

## What Changes

- Models tab 每个 route 从单个 `SimpleSelect` 升级为 `RouteChainEditor`：一个主选择器 +
  `+ add fallback` 追加有序 entry + 每 entry 可 reorder / remove，并有 `override params`
  折叠区（temperature / max_tokens，留空=继承模型注册默认）。渐进式披露：单模型无覆盖的 route
  视觉上与现状一致。
- `configure-logic.ts` 把单值帮助函数（`routeModelId` / `withRouteModel`）泛化为列表版
  `routeEntries` / `withRouteEntries`：解析/写回 `routes[key]` 的 entry 列表，丢弃空 params、
  空链删除 route key、保留兄弟 route 与 credential slot。
- 后端验证（非契约变更）：新增 integration 测试证明「2-entry + per-entry 参数」的
  `model_overrides` 经现有 materialize 展开为 2-target fallback 链且参数正确合并。

## Capabilities

### Modified Capabilities

- `agent-admin-ui`: Models tab 的每个 route 支持配置有序 fallback 链与 per-entry
  temperature/max_tokens 覆盖（此前仅单模型）。

## Module Boundary Impact

- **owning package**: `frontend`（`features/agents` UI + `configure-logic`）。后端
  `platform.agent_lifecycle` / `agent_management_console` 保持现状消费 `model_overrides`。
- **public API surface**: 无新增。复用 `PATCH /admin/agents/{name}` 的 `model_overrides` 字段。
- **owned tables**: 无。schema 不变。
- **config namespace**: `agent.yaml.models.routes`（entry 列表语义已存在）。
- **cross-module dependencies**: 前端依赖 `/admin/models`（带 protocol）过滤候选；无新增后端依赖。
- **migration / shim plan**: 无 schema/迁移。旧的单 entry `model_overrides` 是新列表编辑器的
  退化输入（1 元素链），读写完全兼容；无 shim。
- **depends on**: `expose-agent-model-routes`（提供 Models tab 与 9 路由），stacked 在其分支之上。
