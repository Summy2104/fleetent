## Why

fleetent 已经支持按 `tenant_id + kb_id` 隔离知识库，并且 Google Drive / Confluence connector
可以把企业文档同步到指定 KB。但 agent 运行时还没有明确回答一个关键问题：某个 agent 本次应该检索哪些 KB。

如果继续让 long-term-ctx 直接使用全局默认 KB，Pilot 环境会出现两个问题：

- 不同部门或用途的 agent 无法绑定自己的知识库范围。
- 连接器已经能同步多个 KB，但检索入口仍缺少稳定的可见范围解析 contract。

本 change 增加 agent 到 KB 的绑定边界。默认行为保持保守：没有显式绑定时只访问默认 KB；默认 KB 缺失时降级为空检索并记录诊断事件，不阻断 agent 对话。

## What Changes

- 新增 knowledge-base-owned agent KB binding 表。
- 新增 public API：
  - `bind_agent_to_kb(tenant_id, agent_id, kb_id)`
  - `unbind_agent_from_kb(tenant_id, agent_id, kb_id)`
  - `list_agent_kb_bindings(tenant_id, agent_id)`
  - `resolve_agent_kb_ids(tenant_id, agent_id)`
- `resolve_agent_kb_ids()` 规则：
  - 如果 agent 有显式绑定，返回绑定的 `kb_id` 列表。
  - 如果没有显式绑定，返回 `Settings.knowledge_base.default_kb_id`。
  - 如果默认 KB 未配置或不可用，返回空列表。
- 允许绑定暂不存在的 `kb_id`，支持先配置 agent，再异步创建或同步 KB。
- long-term-ctx built-in knowledge provider 改为通过 `resolve_agent_kb_ids()` 获取 KB 范围，再调用
  `knowledge_base.search()`。
- 默认 KB 缺失或解析为空时，不抛业务错误，不阻断 agent 对话；observability 记录诊断事件。
- 更新 knowledge-base、long-term-ctx、observability 和 roadmap 相关文档。

## Out of Scope

- 不做 HTTP admin API、Admin UI 或 platform UI。
- 不做 document-level ACL。
- 不做 Google Drive / Confluence per-user ACL 映射。
- 不做 Shared Memory。
- 不做 team / tenant shared memory 语义。
- 不做动态 connector credential 管理。
- 不做后台 sync job、scheduler 或 worker。
- 不要求绑定的 KB 必须先存在。

## Module Boundary Impact

- **Owning package**：`intelligence.knowledge_base`。
- **Public API surface**：新增 agent KB binding dataclass / public functions：
  `bind_agent_to_kb()`、`unbind_agent_from_kb()`、`list_agent_kb_bindings()`、
  `resolve_agent_kb_ids()`。
- **Owned tables**：新增 `knowledge_base_agent_bindings`，由 knowledge-base owns。
- **Config namespace**：复用 `knowledge_base.default_kb_id`；不新增配置项。
- **Cross-module dependencies**：long-term-ctx 通过 knowledge-base public API 解析 KB 范围；observability 通过
  public trace/log API 记录默认 KB 缺失诊断。knowledge-base 不反向依赖 long-term-ctx。
- **Migration / shim plan**：新增 additive API 和 Alembic migration；不移动现有 import 路径，不需要 shim。
