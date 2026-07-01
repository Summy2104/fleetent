## D1 — materialize 合并语义：按路由 key 覆盖，而不是整体替换

现状（`_models_from_overrides`，`materialize.py:263-298`）：只要 `model_overrides` 非空，就完全丢弃 `default_models()`，只用 override 里出现的路由重建 `AgentModels`——`targets`/`routes` 都是从空字典开始累加的。

修复：以 `default_models()` 的 `targets`/`routes` 作为合并基线，只有 `model_overrides` 里显式出现的 route key 才覆盖基线里的同名路由（及其引用的 target）；未出现的路由原样保留基线值。

```python
def _models_from_overrides(model_overrides):
    baseline = default_models()
    targets: dict[str, ModelTarget] = {t.id: t for t in baseline.targets}
    routes: dict[str, list[ModelRouteEntry]] = dict(baseline.routes)

    route_overrides = ...  # 现有解析逻辑不变（剥 RESERVED_KEY、拆 routes 块）
    if not route_overrides:
        return baseline

    for route_key, raw_entries in route_overrides.items():
        # 现有的按 entry 构建 target/route_entries 逻辑不变
        route_entries = [...]
        if route_entries:
            routes[str(route_key)] = route_entries  # 覆盖同名路由，其余路由不受影响

    return AgentModels(targets=list(targets.values()), routes=routes)
```

target id 冲突：override target 的 id 就是 `model_admin_store` 的 model id，几乎不会撞上基线固定 id（`default`/`vision`/`embedding`）；万一撞了，override 应该赢（显式配置优先级高于本地假默认），`targets[target.id] = target` 的覆盖写法天然满足这一点。

## D2 — 前端：一个参数化的路由绑定组件，而不是四份手写代码

现状：`OverviewTab` 硬编码一个 `<Select>`，只管 `routes.default`，且不按协议过滤候选模型。

新增一份路由绑定定义表，每个路由的 label/协议过滤都在这里声明一次：

```ts
const ROUTE_BINDINGS = [
  { routeKey: 'default', labelKey: 'agents.modelProvider', protocol: 'openai_chat' },
  { routeKey: 'embedding', labelKey: 'agents.modelEmbedding', protocol: 'http_embedding' },
  { routeKey: 'memory_extraction', labelKey: 'agents.modelMemoryExtraction', protocol: 'openai_chat' },
  { routeKey: 'image_generation', labelKey: 'agents.modelImageGeneration', protocol: 'openai_image_generation' },
] as const;
```

`defaultRouteModelId`/`withDefaultRouteModel` 泛化为 `routeModelId(overrides, routeKey)`/`withRouteModel(overrides, routeKey, modelId)`。`OverviewTab` 对 `ROUTE_BINDINGS` 做一次 `.map()`，每个绑定区用 `allModels.data.filter(m => m.protocol === binding.protocol)` 过滤候选列表，各自独立维护自己的 `modelId` state。保存时依次对 4 个路由调用 `withRouteModel` 叠加到同一份 `model_overrides`，一次 `PUT` 提交（跟现有单路由保存路径一致，只是循环 4 次而不是 1 次）。

## D3 — New model 弹窗：协议 → 字段联动

跟后端 `_ENDPOINT_PROTOCOLS = {"http_embedding", "http_rerank", "openai_image_generation"}` 的校验规则对齐：

| protocol | 需要填的连接字段 |
|---|---|
| `openai_chat` | Base URL |
| `http_embedding` / `http_rerank` / `openai_image_generation` | Endpoint |

表单加一个 protocol 下拉（四个选项，全部走 i18n）；选中值决定渲染 "Base URL" 还是 "Endpoint" 输入框，提交时把值放进 `CreateModelInput` 对应字段（`base_url` 或 `endpoint`，另一个留空）。后端 `ModelBody._validate_connection_fields` 已经做了同样的二选一校验，前端联动只是提前把这个约束体现在表单上，不改后端。

## 测试策略

- **后端合并修复**：unit test，`monkeypatch` `model_admin_store.get_model`/`provider_admin_store.get_provider`（沿用 model-registry-split 时期 `_target_from_model_override` 测试的既有模式，不碰真实 DB），断言只覆盖 `default` 路由时，`memory_extraction`/`embedding`/`vision` 仍解析到 `default_models()` 的基线 target。
- **New model 弹窗**：`frontend/src/features/providers/page.test.tsx` 补场景——切到 `http_embedding` 协议后字段变成 Endpoint、提交 payload 带 `protocol`+`endpoint`（不带 `base_url`）；中文 locale 下弹窗标题/字段/按钮文案是中文。
- **Agent 路由绑定**：新建 `frontend/src/features/agents/configure.test.tsx`——覆盖 4 个绑定区各自独立渲染并预填已有绑定、候选列表按协议过滤（embedding 区不出现 chat 模型）、保存后 4 个路由的 `model_id` 都出现在 `PUT` payload 的 `model_overrides.routes` 里且互不覆盖彼此。
