## Why

现在的 agent 配置页只能给 `default` 这一条路由挂一个模型，其余标准路由（`embedding`/`memory_extraction`/`image_generation` 等）完全没有 UI 入口；"New model"创建弹窗还硬编码 `protocol=openai_chat`、文案全英文，而后端早就支持 `http_embedding`/`http_rerank`/`openai_image_generation` 三种协议，中文 i18n 基础设施也已就位（同页的"新建供应商"弹窗就是双语的）。

排查过程中发现一个潜伏 bug：`agent_lifecycle/materialize.py::_models_from_overrides` 只要 `agents.model_overrides` 里出现任意一个路由 key，就整体丢弃 `default_models()` 的其余路由，而不是按路由合并——也就是说任何 agent 一旦通过现有"Model Provider"下拉框自定义过 `default` 模型，它的 `memory_extraction`/`kb_extraction`/`vision`/`embedding` 路由会**静默消失**（不报错，功能悄悄降级为本地假实现）。这是本次新增"按路由独立绑定"能正确工作的前提，必须先修，否则新绑定区一保存就会把其它路由挤没。

另外核实到 `openspec/specs/provider-admin-ui/spec.md` 已有一条"Agent model routes are first-class in the console"需求（2026-06-28 model-registry-split 承诺、tasks.md 标了完成），但代码从未交付；其中的"回退链多选"场景跟本次要交付的"每路由独立单选"不一致，本次顺手把这条 spec 收紧到跟真实交付对齐。

## What Changes

- 修复 `materialize.py::_models_from_overrides`：以 `default_models()` 为基线按路由 key 合并覆盖；未被 `model_overrides` 显式提及的路由保留默认 target，不再因为其它路由被覆盖而整体消失。
- "New model"创建弹窗（`frontend/src/features/providers/page.tsx`）：接入 i18n（中英双语，沿用 `providers.*` 命名空间）；新增协议选择器，覆盖 `openai_chat`/`http_embedding`/`http_rerank`/`openai_image_generation`；表单字段随协议联动显示 "Base URL" 或 "Endpoint"。
- Agent 配置页（`frontend/src/features/agents/configure.tsx`）新增三个独立单选绑定区（Embedding / Memory extraction / Image generation），并把现有 `default` 绑定区一并按协议过滤候选模型列表；把原本硬编码的单个 Select 抽成参数化的路由绑定渲染，`defaultRouteModelId`/`withDefaultRouteModel` 泛化为按 `routeKey` 参数化的辅助函数。
- **收紧 spec**：`provider-admin-ui` 的"Agent model routes are first-class in the console"需求删除"Fallback chain editing"场景，路由范围改为精确列出本次交付的四个（`default`/`embedding`/`memory_extraction`/`image_generation`）。

**范围外**（本次不做）：`vision`/`kb_extraction`/`rerank` 路由的独立绑定 UI（merge fix 后它们会继续正常保留默认值，不会被这次改动破坏，只是没有"改成非默认模型"的入口）；多模型回退链 UI；per-agent provider key override（已实现，不动）；后端 `/admin/models` API（协议校验已支持四种协议，无需改动）。

## Capabilities

### Modified Capabilities
- `agent-scoped-model-routing`：「Platform materializes model config」需求新增合并语义——未被 `model_overrides` 显式覆盖的标准路由必须保留 `default_models()` 的默认 target。
- `provider-admin-ui`：「Agent model routes are first-class in the console」收紧为四个具体路由 + 独立单选（删除回退链场景）；「Provider CRUD and connectivity」补充协议覆盖场景（New model 表单支持四种协议选择 + 中英文案）。

## Impact

- **owning package**：`fleetent.platform.agent_lifecycle`（`materialize.py`）+ 前端 `features/providers`、`features/agents`、`i18n`。
- **public API surface**：无新增/变更接口，复用既有 `POST /admin/models`、`PUT /admin/agents/{name}`。
- **owned tables**：无，`agents.model_overrides` 字段结构不变，只是内容里能出现更多 route key。
- **config namespace**：无新增。
- **cross-module dependencies**：无新增；`agent_lifecycle` 仍是唯一调用 `model_admin_store`/`provider_admin_store` 的位置；agent 运行时对本次改动零感知（只读 materialize 后的 `agent.yaml`）。
- **migration / shim plan**：无需要。`_models_from_overrides` 的修复对已有 `model_overrides` 数据是纯粹的正向修复（消失的默认路由会在下次 materialize 时自动"捡回"），无需迁移脚本、无需 shim。
