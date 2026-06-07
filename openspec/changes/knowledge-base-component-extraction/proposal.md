> **状态：DRAFT — 待 Randy 讨论修订**。本 change 含多个未决设计决策（见末尾「待讨论决策点」），design/tasks 待讨论后补。

## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段2**。KB 当前在 `intelligence/knowledge_base/`，读写管理混在一起（`runtime.py` 一个文件里 KB CRUD + ingest + search 全有），且整体挂在 agent runtime 业务树下。本 change 把 KB 提为顶层独立组件，并三分为 `core / retrieval / ingest`，确立"读边界给 agent、写边界由 platform 驱动"。

## What Changes（轮廓，细节待讨论）

- **物理迁移**：`intelligence/knowledge_base/` → 顶层 `knowledge_base/`（同 vector_store 模式，留 re-export shim）。
- **三分**：
  - `core/`：store + models（域内读写共享底层）。
  - `retrieval/`：search / graph_search / scope 解析（agent 读边界，只读 core；预留 agent 自主写入口）。
  - `ingest/`：connectors / parsers / sync / extraction / KB CRUD（写边界，由 platform 驱动）。
- **拆 `runtime.py`**：search 系 → retrieval；ingest/CRUD/delete → ingest；rerank 辅助随 retrieval。
- **拆 `bindings.py`**：scope 解析（读，agent）/ 绑定管理（写，platform 驱动）。
- **依赖护栏**：`retrieval ✗→ ingest`；agent runtime 只 import `knowledge_base.retrieval`。

## Capabilities

### New Capabilities
<!-- 暂定，待讨论 -->

### Modified Capabilities
- `knowledge-base`：requirement 不变行为，但重组为 retrieval/ingest 边界；新增"读写边界"与"依赖护栏"requirement。具体 delta 待决策点定稿后写。

## Impact

- 物理移动 + shim（沿用 roadmap Shim 策略）。
- 调用方：agent 侧（long_term_ctx 等）改 import `knowledge_base.retrieval`；platform（kb_admin_api / admin_cli）改 import `knowledge_base.ingest`。
- 依赖阶段1（vector_store 已在顶层）。

## 待讨论决策点（DRAFT — 明天讨论）

1. **ingest 的归属与"platform 驱动"的接口形态**：ingest 领域逻辑放 `knowledge_base/ingest`（组件内，platform 调用它）还是上移进 `platform/knowledge_base_management`？纲领倾向前者（组件内 + platform 驱动），但"驱动"的 API 边界要定清楚。
2. **connector 定义双源**：现状 `get_connector_config` 读 agent 侧 `_kb_config`，而 platform 有 `kb_connectors` 表——两个源。重构要不要统一？统一到哪侧？（CLAUDE.md 点名 `knowledge_base/config` 是待审计的 agent→platform 依赖。）
3. **core 读写边界的暴露方式**：`store.py` 读写方法混在一类里。retrieval 只该拿到读方法、ingest 拿读写——是拆成 `ReadStore`/`WriteStore` 两个接口，还是靠约定 + 护栏约束？
4. **KB CRUD（建库/删库/绑定管理）归属**：算 ingest 写边界，还是单独的"KB 管理"？它由 platform 调用，但不是"摄取外部数据"。
5. **graph 的 extraction（建图）归 ingest**确认：实体/关系抽取是对已摄取文档的加工，归 ingest 写边界；graph_search 归 retrieval 读。边界处（共享 entity/relation 表）怎么切。
6. **agent 自主写入口子**：纲领要求 retrieval 侧预留"agent 自主沉淀/reflection 改进写 KB"的入口——这个写入口和 ingest 写边界如何共存（都经 core？是否经审批门）。
