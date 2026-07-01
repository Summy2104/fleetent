# Tasks — agent-model-route-bindings

> 规则：每个实现 task 的测试 task 在其之前（TDD hard gate）。test 见红 → impl 见绿。
> 层边界：materialize 用 monkeypatch 隔离真实 DB → unit；前端组件测试 → frontend test（vitest + RTL + msw）。

## 1. 后端：materialize 路由合并修复

- [ ] 1.1 (unit test) 在 materialize 的既有测试文件里补测试：`model_overrides` 只覆盖 `default` 路由时，`_models_from_overrides` 的返回结果里 `memory_extraction`/`embedding`/`vision` 路由仍解析到 `default_models()` 的基线 target（monkeypatch `model_admin_store.get_model`/`provider_admin_store.get_provider`，不碰真实 DB）
- [ ] 1.2 实现 `_models_from_overrides`：以 `default_models()` 为基线合并，按 route key 覆盖而不是整体替换（D1）

## 2. "New model" 弹窗：i18n + 四协议支持

- [ ] 2.1 (frontend test) `frontend/src/features/providers/page.test.tsx` 补场景：协议选择器切到 `http_embedding` 后表单渲染 Endpoint 而非 Base URL，提交 payload 含 `protocol: 'http_embedding'` + `endpoint`（不含 `base_url`）；中文 locale 下弹窗标题/字段 label/按钮文案为中文
- [ ] 2.2 `frontend/src/i18n/messages.ts` 补齐 `providers.newModelDialog*`/`providers.fieldModelId`/`providers.fieldModelName`/`providers.fieldProtocol`/`providers.fieldEndpoint` 等 key 的中英文案
- [ ] 2.3 `frontend/src/features/providers/page.tsx` 的 `ModelFormDialog` 接入 `useT()`；`ModelFormState` 加 `endpoint` 字段；新增协议 `<Select>`（四选项）；按协议联动渲染 Base URL 或 Endpoint 输入框；`submitModel` 按协议把值放进对应字段

## 3. Agent 配置页：Embedding / Memory extraction / Image generation 独立绑定区

- [ ] 3.1 (frontend test) 新建 `frontend/src/features/agents/configure.test.tsx`：断言 4 个路由绑定区（default/embedding/memory_extraction/image_generation）各自独立渲染并预填 `model_overrides` 里已有的绑定；embedding 候选列表不出现 chat 协议模型；保存后 `PUT` payload 的 `model_overrides.routes` 同时包含 4 个路由且互不覆盖
- [ ] 3.2 `frontend/src/i18n/messages.ts` 补齐 `agents.modelEmbedding`/`agents.modelMemoryExtraction`/`agents.modelImageGeneration` 等中英文案
- [ ] 3.3 `frontend/src/features/agents/configure.tsx`：泛化 `defaultRouteModelId`/`withDefaultRouteModel` 为按 `routeKey` 参数化；加 `ROUTE_BINDINGS` 定义表（D2）；`OverviewTab` 按定义表渲染 4 个绑定区，各自按协议过滤 `allModels.data`

## 4. Spec 收紧（非代码产物，人工确认内容后再提交，不受 TDD gate 约束）

- [ ] 4.1 `openspec/changes/agent-model-route-bindings/specs/agent-scoped-model-routing/spec.md`：MODIFIED「Platform materializes model config」，新增合并语义场景
- [ ] 4.2 `openspec/changes/agent-model-route-bindings/specs/provider-admin-ui/spec.md`：MODIFIED「Agent model routes are first-class in the console」（删回退链场景、路由范围改为四个具体路由）+ MODIFIED「Provider CRUD and connectivity」（补协议覆盖场景）

## 5. 收尾

- [ ] 5.1 `make test-pr` + `make test-integration-ci` 全绿（无新增失败）；改动文件 ruff/mypy 通过；`cd frontend && yarn test` 全绿
- [ ] 5.2 手动验证 golden path：起 `uvicorn` + frontend dev server，在浏览器里新建一个 `http_embedding` 协议的模型 → 在某 agent 的 Embedding 绑定区选中它并保存 → 确认该 agent 的 Memory extraction/其它路由未被清空（读 `GET /admin/agents/{name}` 的 `model_overrides` 或 export 的 `agent.yaml` 核实）
