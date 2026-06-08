## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段2**。KB 当前在 `intelligence/knowledge_base/`，读、写、管理混在一起（`runtime.py` 一个文件里 KB 容器 CRUD + ingest + search 全有；`store.py` 读写方法同一类；`bindings.py` scope 读 + 绑定写混），整体挂在 agent runtime 业务树下。本 change 把 KB 提为顶层独立组件（未来服务雏形），按职责四分，确立"**读边界给 agent、写边界由 platform 驱动、KB 内容写入路径单一**"。

## What Changes

- **物理迁移**：`intelligence/knowledge_base/` → 顶层 `knowledge_base/`（同 vector_store 模式，留 re-export shim）。
- **四块结构**（纲领 §5）：
  - `core/`：`store`（暴露 **Readable / Writable 两个 Protocol、一份实现** `KnowledgeStore`）+ `models`。域内读写共享底层。
  - `retrieval/`：`search` / `graph_search` / `scope`（绑定解析）。agent 读边界，**类型上只见 Readable**，只 import core 的读接口。
  - `ingest/`：`connectors` / `parsers` / `sync` / `extraction` + KB **内容写**（ingest/chunk/document delete-archive/图谱抽取）。platform 驱动，**唯一写 KB 内容的路径**。
  - `management/`：建库 / 归档 / 改描述 + agent↔KB 绑定。容器/绑定写，platform 驱动。
- **KB 写入单一化**（纲领 §4）：KB 是**派生视图**，retrieval 侧**不预留** agent 自主写入口；agent 贡献经 agent-curated 沉淀源 → connector sync 流入 KB，保证 KB 始终是数据源的纯派生、可追溯、可重新摄取。
- **connector 双源消解**：ingest 做成**接收 settings 的纯函数**（`as_knowledge_base_settings` 注入模式）——不再自读 agent 侧 `_kb_config`，由 platform 把 connector 配置注入。注入模式即答案，消除"agent config vs platform `kb_connectors` 表"双源。
- **依赖护栏**：`retrieval ✗→ ingest`；agent runtime 只 import `knowledge_base.retrieval`；组件 ✗→ platform。

## Capabilities

### New Capabilities
- `knowledge-base-boundaries`: 把 KB 四块边界契约固化为 spec——core 读写 Protocol、retrieval 只读、ingest 唯一内容写入路径（KB 写入单一化）、management 容器/绑定写、依赖护栏（retrieval✗→ingest、组件✗→platform）、ingest settings 注入消解 connector 双源。

### Modified Capabilities
- `knowledge-base`：行为不变，但读写重组为 retrieval/ingest 边界；具体 delta 在 `knowledge-base-boundaries` 表达，`knowledge-base` 本体行为契约不动。

## Impact

- **物理移动**：`intelligence/knowledge_base/`（20 文件）→ `knowledge_base/{core,retrieval,ingest,management}/` + shim（沿用 roadmap Shim 策略）。
- **拆 `runtime.py`(530)**：search 系（search/_search_vector/_search_hybrid/rerank helpers）→ retrieval；ingest/CRUD/document delete-archive → ingest；建库/归档/改描述 → management。
- **拆 `bindings.py`(181)**：`resolve_agent_kb_ids`/`_get_binding`（scope 读）→ retrieval；`bind/unbind/list_agent_kb_bindings`（绑定写）→ management。
- **拆 `store.py`(542)**：抽 Readable/Writable Protocol，retrieval 仅依赖 Readable。
- **调用方**：agent 侧（`long_term_ctx`）改 import `knowledge_base.retrieval`；platform（`knowledge_base_management/kb_admin_api`、`admin_cli`）改 import `knowledge_base.ingest` / `.management`，并改为向 ingest 注入 settings。
- **CLAUDE.md**：契约文字留阶段5 统一改；本 change 先动代码 + shim。
- **依赖**：阶段1（vector_store 已在顶层）。
- **不含**：检索/rerank/embedding 逻辑变更、namespace 约定变更、connector 协议变更。
