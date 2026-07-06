## Context

`expose-agent-model-routes` 让 Models tab 为 9 个标准 route 各渲染一个单选 `SimpleSelect`
（`configure.tsx` 的 `ROUTE_BINDINGS` 循环），保存时 `withRouteModel` 写单元素
`routes[key]=[{model_id}]`。运行时按 route 消费：`resolve(route_key)` 返回有序链，
`call_with_policy` 逐个尝试、`ModelCallSwitchableError` 降级（`model/resolver.py`）。

后端 `_models_from_overrides`（`materialize.py:263`）已按列表遍历每个 route 的 entry，逐个经
`_target_from_model_override` 建 target，并 `ModelRouteEntry(target, max_tokens=raw.max_tokens,
params=raw.params)`。所以**多 entry + per-entry 参数早已端到端可用**——UI 只是从没写过多 entry。

## Goals / Non-Goals

**Goals**
- 每个 route 可配有序 fallback 链（primary → fallback → …）。
- 每个 entry 可覆盖 temperature（存 `params.temperature`）与 max_tokens（存 entry 原生
  `max_tokens`），留空=继承模型注册默认。
- 渐进式披露：单模型、无覆盖的 route 视觉负担与现状持平。
- 读写与旧单 entry `model_overrides` 双向兼容。

**Non-Goals**
- 不暴露显式 named-target 编写（复用经 model id 自动完成）。
- 不暴露 temperature/max_tokens 以外的 params（top_p/stop 等仍走手写 YAML）。
- 不改后端 API / schema / materialize；不改运行时 resolver / call_with_policy。
- 不动 default 路由的特殊呈现、reserved audio 空态、provider-key override 的既有语义。

## Decisions

### D1 — entry 存储形状

`routes[key]` 存 entry 列表，每 entry：
```jsonc
{ "model_id": "openai-gpt4", "max_tokens": 4096, "params": { "temperature": 0.7 } }
```
`max_tokens` 空则省略键；`params.temperature` 空则省略 `params`；两者皆空则 entry 仅 `{model_id}`。
这与 `_models_from_overrides` 读取的 `raw_entry.get("model_id"/"max_tokens"/"params")` 完全对齐，
`resolve` 时 `_merge` 用 `{**target.params, **entry.params}` + `entry.max_tokens ?? target.max_tokens`
生效（`resolver.py:155`）。

### D2 — 帮助函数泛化到 `configure-logic.ts`（纯函数，单测覆盖）

- `routeEntries(overrides, routeKey): Array<{modelId, temperature?, maxTokens?}>`——从
  `routes[routeKey]` 逐 entry 解析：modelId 取 `model_id`（回落 `provider_id/target/provider`，
  兼容旧存法），temperature 取 `params.temperature`，maxTokens 取 `max_tokens`。
- `withRouteEntries(overrides, routeKey, entries): AgentModelOverrides`——重建 `routes[routeKey]`：
  过滤掉无 modelId 的 entry；空链 `delete routes[routeKey]`；每 entry 只在有值时写
  `max_tokens` / `params.temperature`；保留其它 route 与 credential slot（沿用 `withRouteModel`
  的 sibling 保护）。

单值旧函数 `routeModelId` / `withRouteModel` 保留或以 `routeEntries`/`withRouteEntries` 实现，
避免破坏既有引用。

### D3 — `RouteChainEditor`（渐进式披露）

每个 route 一个实例，替换现有单 `SimpleSelect` 块：
- 主 entry 为醒目单选；`+ add fallback` 追加 entry（末位 entry 未选模型前禁用「add」）。
- ≥2 entry 时每行出现 reorder（↑↓）与 remove（✕）；单 entry 时隐藏 reorder。
- 每 entry 一个 `override params` 折叠区：temperature、max_tokens 两个数字输入（可空）。
- 候选按 route protocol 过滤（不变）；**同一链内已选模型从其它 entry 候选中剔除**（去重，
  避免同 target 重复重试）。
- reserved audio 空态提示不变（候选为空且链为空时显示）。
- viewer 只读：每 entry 呈现 `model_id · temp/max` 摘要，无编辑控件。

### D4 — provider-key override 绑定主 entry

provider-key override section 继续绑定 **entry 0** 的模型所属 provider（沿用现逻辑），fallback
entry 用各自注册的 provider key。避免多 entry 引出多 key 编辑的复杂度（YAGNI）。

### D5 — 后端只验证不改契约

不改 `UpdateBody.model_overrides`（free-form dict）。新增 integration 测试锁「多 entry + 参数」
经 materialize 展开为多 target fallback 链、参数正确合并，防止后续给 `model_overrides` 加校验时
静默破坏 fallback。

## Error Handling / Validation

- temperature / max_tokens 数字输入，空=省略（继承）。非法值（非数字/负数）→ 该字段不写入，
  不硬报错（对齐 `_apply_overrides` 的容错风格）。
- 绝不写 `routes[key]: []`（`AgentModels` 校验会拒「route 至少一个 target」）——空链一律删键。
- 无新增服务端校验。

## Testing

- 后端（verify-only，integration，`test_agent_materialize_export.py`）：`default` 2-entry +
  per-entry temperature/max_tokens → 展开为 2-target 链、`_merge` 后参数正确。
- 前端 unit（`configure-logic.test.ts`）：`routeEntries` 解析多 entry + 参数；`withRouteEntries`
  round-trip、丢空 params、空链删键、保留 siblings + credential slot。
- 前端组件（`configure.test.tsx`）：加 fallback + 设 temperature → Save 断言 PATCH body 为
  2-entry 链且含 `params.temperature`；reorder 改变保存顺序；单模型 route 仍存 1-entry 链（回归保护）。
- 回归：`page.test.tsx` 既有 model-binding 用例（单选 round-trip / provider-key）在新编辑器下仍绿。

## Risks / Trade-offs

- **9 个 route × 链编辑器的视觉密度**：靠渐进式披露缓解（默认仍是单选外观）。
- **旧存储读回**：旧单 entry（`{model_id}` / 旧 `provider_id` 风格）必须被 `routeEntries` 正确解析为
  1-entry 链——单测显式覆盖。
- **`page.test.tsx` 既有用例**：单选交互路径改成链编辑器后，选择/保存的 DOM 结构可能变，需同步更新。

## Open Questions

- 是否需要给 fallback entry 也暴露 provider-key override？当前 D4 只绑主 entry；如运维确有
  「主备用不同 key」需求，可后续加，不在本 change。
