## REMOVED Requirements

### Requirement: Agent knowledge-base binding public API
**Reason**: 该 requirement 描述 knowledge_base 模块自持的绑定 API（`bind_agent_to_kb` / `unbind_agent_from_kb` / `list_agent_kb_bindings` / `resolve_agent_kb_ids`）与 `knowledge_base_agent_bindings` 表——经核实为**死路径**：该表全仓无写入点、解析器无活调用方。agent↔KB 绑定的真相源是平台 `agent_kbs`（见 `kb-agent-binding`）。
**Migration**: 绑定管理用平台 `agent_kbs`（`kb-agent-binding` spec：admin 经 `kb_admin_api` 写、带审计）；agent 侧的有效 KB 范围由 `agent_kbs` 经 `materialize` 沉淀进 `agent.knowledge`（`AgentKnowledge`），运行时由 `long-term-ctx` 读取（见 `long-term-ctx`「Long-term context uses agent KB bindings」）。

### Requirement: Agent KB binding behavior
**Reason**: 描述死路径的 `bind_agent_to_kb` / `unbind_agent_from_kb` 幂等与隔离行为；这些写操作已无生产调用，绑定写入归平台 `agent_kbs`。
**Migration**: 绑定的幂等/租户隔离/agent 隔离由平台 `agent_kbs`（`kb-agent-binding`）保证。

### Requirement: Agent KB scope resolution
**Reason**: `resolve_agent_kb_ids()` 是死解析器（无活调用方）；agent 有效 KB 范围不再由它解析。
**Migration**: 有效 KB 范围 = `agent.knowledge` 中已 materialize 的 bindings（源自 `agent_kbs`）；`long-term-ctx` 据此检索，空范围时优雅降级（见 `long-term-ctx`）。「search 传入不存在/空 KB 返回空结果」的行为由 knowledge-base 搜索相关 requirement 保证，不依赖本解析器。
