## ADDED Requirements

### Requirement: Agent knowledge-base binding public API
系统 SHALL 提供 agent 到 knowledge base 的绑定 public API，用于声明某个 tenant 下的 agent 可以检索哪些 KB。

#### Scenario: Binding API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `AgentKnowledgeBaseBinding`、
  `bind_agent_to_kb`、`unbind_agent_from_kb`、`list_agent_kb_bindings` 和 `resolve_agent_kb_ids`
- **THEN** 导入成功

#### Scenario: Binding table exists
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 knowledge-base-owned `knowledge_base_agent_bindings` 表
- **AND** 表对 `tenant_id + agent_id + kb_id` 施加唯一约束

### Requirement: Agent KB binding behavior
系统 SHALL 支持按 tenant 和 agent 管理显式 KB 绑定，且绑定行为保持幂等和隔离。

#### Scenario: Bind is idempotent
- **WHEN** 对同一 `tenant_id`、`agent_id` 和 `kb_id` 重复调用 `bind_agent_to_kb()`
- **THEN** 系统只保留一条绑定
- **AND** 调用不会因重复绑定失败

#### Scenario: Unbind is idempotent
- **WHEN** 对不存在的绑定调用 `unbind_agent_from_kb()`
- **THEN** 系统不报错

#### Scenario: Binding is tenant isolated
- **WHEN** 不同 tenant 中存在同名 agent 的 KB 绑定
- **THEN** 查询其中一个 tenant 的绑定不会返回另一个 tenant 的 KB

#### Scenario: Binding is agent isolated
- **WHEN** 同一 tenant 中不同 agent 绑定到不同 KB
- **THEN** 查询其中一个 agent 的绑定不会返回另一个 agent 的 KB

#### Scenario: Empty binding identifiers are rejected
- **WHEN** `tenant_id`、`agent_id` 或 `kb_id` 为空
- **THEN** 系统 fail fast

#### Scenario: Binding may reference future KB
- **WHEN** 调用 `bind_agent_to_kb()` 绑定当前尚不存在或尚无内容的 `kb_id`
- **THEN** 系统允许保存绑定

### Requirement: Agent KB scope resolution
系统 SHALL 提供 `resolve_agent_kb_ids(tenant_id, agent_id)` 作为 agent 有效 KB 范围的唯一解析入口。

#### Scenario: Explicit bindings override default KB
- **WHEN** agent 存在一个或多个显式 KB 绑定
- **THEN** `resolve_agent_kb_ids()` 返回显式绑定的 KB 列表
- **AND** 不额外返回默认 KB

#### Scenario: Missing binding falls back to default KB
- **WHEN** agent 没有显式 KB 绑定
- **AND** `Settings.knowledge_base.default_kb_id` 已配置
- **THEN** `resolve_agent_kb_ids()` 返回只包含默认 KB 的列表

#### Scenario: Missing default KB returns empty scope
- **WHEN** agent 没有显式 KB 绑定
- **AND** 默认 KB 未配置、为空或不可用
- **THEN** `resolve_agent_kb_ids()` 返回空列表
- **AND** 系统记录可诊断事件
- **AND** 系统不抛出阻断 agent 对话的业务错误

#### Scenario: Search with future or empty KB returns no chunks
- **WHEN** 调用 `knowledge_base.search()` 并传入不存在或暂无内容的 `kb_id`
- **THEN** 系统返回空结果
- **AND** 不把该情况视为绑定错误
