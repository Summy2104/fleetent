# Tasks — agent-model-route-bindings

> 规则：每个实现 task 的测试 task 在其之前（TDD hard gate）。test 见红 → impl 见绿。
> 层边界：materialize 用 monkeypatch 隔离真实 DB → unit；前端组件测试 → frontend test（vitest + RTL + msw）。

## 1. 后端：materialize 路由合并修复

- [x] 1.1 (unit test) 在 materialize 的既有测试文件里补测试：`model_overrides` 只覆盖 `default` 路由时，`_models_from_overrides` 的返回结果里 `memory_extraction`/`embedding`/`vision` 路由仍解析到 `default_models()` 的基线 target（monkeypatch `model_admin_store.get_model`/`provider_admin_store.get_provider`，不碰真实 DB）
- [x] 1.2 实现 `_models_from_overrides`：以 `default_models()` 为基线合并，按 route key 覆盖而不是整体替换（D1）

## 2. "New model" 弹窗：i18n + 四协议支持

- [x] 2.1 (frontend test) `frontend/src/features/providers/page.test.tsx` 补场景：协议选择器切到 `http_embedding` 后表单渲染 Endpoint 而非 Base URL，提交 payload 含 `protocol: 'http_embedding'` + `endpoint`（不含 `base_url`）；中文 locale 下弹窗标题/字段 label/按钮文案为中文
- [x] 2.2 `frontend/src/i18n/messages.ts` 补齐 `providers.newModelDialog*`/`providers.fieldModelId`/`providers.fieldModelName`/`providers.fieldEndpoint` 等 key 的中英文案（`providers.fieldProtocol` 已存在，直接复用）
- [x] 2.3 `frontend/src/features/providers/page.tsx` 的 `ModelFormDialog` 接入 `useT()`；`ModelFormState` 加 `endpoint` 字段；新增协议 `<Select>`（四选项）；按协议联动渲染 Base URL 或 Endpoint 输入框；`submitModel` 按协议把值放进对应字段；顺手把 `ProviderCard` 上触发弹窗的"New model"按钮也接入 i18n

## 3. Agent 配置页：Embedding / Memory extraction / Image generation 独立绑定区

- [x] 3.1 (frontend test) 实际测试文件是 `frontend/src/features/agents/page.test.tsx`（configure 页的测试历来都放在这里，而不是单独的 configure.test.tsx）：在既有「agents configure page model binding」describe 块里新增场景，断言 4 个路由绑定区（default/embedding/memory_extraction/image_generation）各自独立渲染并预填 `model_overrides` 里已有的绑定；embedding 候选列表不出现 chat 协议模型；保存后 `PATCH` payload 的 `model_overrides.routes` 同时包含 4 个路由且互不覆盖。顺手把已有的"round-trips the model provider selection"测试的裸 `getByRole('combobox')` 改成按 `name` 精确匹配（新增 3 个 combobox 后裸选择器会变得有歧义）
- [x] 3.2 `frontend/src/i18n/messages.ts` 补齐 `agents.selectModel`/`agents.modelEmbedding`/`agents.modelMemoryExtraction`/`agents.modelImageGeneration` 等中英文案
- [x] 3.3 `frontend/src/features/agents/configure.tsx`：泛化 `defaultRouteModelId`/`withDefaultRouteModel` 为 `routeModelId`/`withRouteModel`（按 `routeKey` 参数化）；加 `ROUTE_BINDINGS` 定义表（D2）；`OverviewTab` 按定义表渲染 4 个绑定区，各自按协议过滤 `allModels.data`，`SelectTrigger` 加 `aria-label` 以便测试/无障碍区分

## 4. Spec 收紧（非代码产物，人工确认内容后再提交，不受 TDD gate 约束）

- [x] 4.1 `openspec/changes/agent-model-route-bindings/specs/agent-scoped-model-routing/spec.md`：MODIFIED「Platform materializes model config」，新增合并语义场景（proposal 提交时已写好）
- [x] 4.2 `openspec/changes/agent-model-route-bindings/specs/provider-admin-ui/spec.md`：MODIFIED「Agent model routes are first-class in the console」（删回退链场景、路由范围改为四个具体路由）+ MODIFIED「Provider CRUD and connectivity」（补协议覆盖场景）（proposal 提交时已写好）

## 5. 收尾

- [x] 5.1 `make test-pr` + `make test-integration-ci` 全绿（无新增失败）；改动文件 ruff/mypy 通过；`cd frontend && yarn test`/`yarn tsc --noEmit`/`yarn lint` 全绿。过程中发现并修复了 merge fix 暴露的 2 处旧测试（`test_agent_materialize_export.py`、`test_node_desired_state_api.py`）对"覆盖任意路由=其余路由全消失"这个旧 bug 行为的隐式断言，已改写为断言新的合并语义；另加了一条 unit test 覆盖"某 baseline target 的所有引用路由都被覆盖后，该 target 应被裁剪"的场景（materialize.py 在 D1 基础上做了收敛，避免遗留不再被任何路由引用的僵尸 target）
- [x] 5.2 手动验证 golden path（`make dev-bootstrap` + `make platform` + `yarn dev`，playwright 实机点击）：新建 provider + 一个 `http_embedding` 模型（bge-small-embed）+ 一个 `openai_chat` 模型（llama3-chat）→ New model 弹窗中文文案 + 协议切到 http_embedding 后 Base URL 换成 Endpoint，均验证通过 → 新建 agent → Embedding 绑定区下拉只列出 bge-small-embed（不含 llama3-chat）、Memory extraction 绑定区下拉只列出 llama3-chat（不含 bge-small-embed）→ 分别选中并保存 → 直查 DB 确认 `model_overrides` 同时含 `embedding`+`memory_extraction` 两条路由且互不覆盖、`default` 未被强制写入 → 再跑 `materialize.agent_file_from_store` 确认 `default`/`kb_extraction`/`vision`（均未显式配置）仍解析到 baseline target，`memory_extraction`/`embedding` 解析到刚绑定的模型——merge fix 端到端生效。验证环境用临时端口 8766 + 独立 `.fleetent-dev`，未影响其它 worktree 上跑着的服务
