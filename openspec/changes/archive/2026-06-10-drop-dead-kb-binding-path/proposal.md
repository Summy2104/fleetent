## Why

agent↔KB 绑定今天有**一活一死**两条路径，造成 §4-④「重复绑定」的假象：

- **活路径**：admin 经 `kb_admin_api` 写 `agent_kbs`（带 `created_by` 审计）→ `materialize._knowledge_for_agent` 读 `agent_kbs` 构造 `AgentKnowledge`（agent 配置 `knowledge` 块）→ 运行时 `long_term_ctx` 读 `agent.knowledge` → `kb_ids` → `retrieval.search`。`kb-agent-binding` spec 已把 `agent_kbs` 定为权威源。
- **死路径**：`knowledge_base_agent_bindings` 表（alembic 012）**全仓无写入点**；`knowledge_base/bindings.py:resolve_agent_kb_ids` **无活调用方**（仅 export + 两个自测）。

但 `knowledge-base` 与 `long-term-ctx` 两个 spec 仍把死路径写成现行设计（`resolve_agent_kb_ids` 为「唯一解析入口」），与已落地的 `AgentKnowledge` 模型**脱节**。本 change 删死路径 + 把这两个 spec 校正到现实。

## What Changes

- **drop 死表 `knowledge_base_agent_bindings`**（新增 alembic 迁移；它是管理库 alembic-owned 表）。
- **删死代码**：`knowledge_base/bindings.py`（`list_agent_kb_bindings` / `resolve_agent_kb_ids` / `AgentKnowledgeBaseBinding` / 私有 helper）、`knowledge_base/retrieval/scope.py`（其仅 re-export 死路径），以及 `knowledge_base/__init__.py`、`retrieval/__init__.py` 的相关导出。
- **处理两个自测死路径的测试**：`tests/integration/test_knowledge_base_agent_bindings.py`、`tests/unit/test_knowledge_base_retrieval_contracts.py`（删除或重指向 `agent_kbs` 活路径）。
- **校正 spec 到 AgentKnowledge 模型**：`knowledge-base` 移除「经 `knowledge_base_agent_bindings` / `resolve_agent_kb_ids` 解析 agent KB 范围」相关 requirement；`long-term-ctx` 把「recall 范围来源」从 `resolve_agent_kb_ids` 改为已 materialize 的 `agent.knowledge` bindings。

不在本切片：`agent_kbs`（活真相源，不动）；`materialize._knowledge_for_agent` / `long_term_ctx` 读 `agent.knowledge` 的实现（已是现行行为，不改）；任何 #3 路由 / 物理库改动（本 change 与持久层 #3 解耦）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `knowledge-base`: 移除「agent KB 绑定经 `knowledge_base_agent_bindings` 表 + `resolve_agent_kb_ids` 解析」的 requirement——agent KB 范围由平台 `agent_kbs`（见 `kb-agent-binding`）materialize 进 `agent.knowledge` 决定，knowledge_base 模块不再持有绑定表/解析器。
- `long-term-ctx`: 「Long-term context uses agent KB bindings」requirement 的范围来源由 `knowledge_base.resolve_agent_kb_ids()` 改为已 materialize 的 `agent.knowledge` bindings（去除对死路径的引用）。

## Impact

- **数据/schema**：drop `knowledge_base_agent_bindings`（管理库，alembic 迁移；无数据——本就无写入）。
- **代码**：删 `knowledge_base/bindings.py`、`retrieval/scope.py` 死路径 + 相关 export；不动 `agent_kbs_store`、`materialize`、`long_term_ctx` 活路径。
- **约束遵守**：管理库表 drop 走 **alembic**（`knowledge_base_agent_bindings` 是 alembic-owned）；不得 `import fleetent.platform.*`；统一经 `db.py` 边界。
- **安全前提**：动手前先以测试断言「该表生产无写入路径、可安全 drop」。
- **依赖文档**：data-model.md §4-④（已记本结论）。
