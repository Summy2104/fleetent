## Context

当前知识库已经有以下基础：

- `tenant_id + kb_id` 作为知识库作用域。
- `knowledge_base.search(query, tenant_id, kb_ids, limit, mode)` 支持多个 KB 检索。
- long-term-ctx 可选调用 knowledge-base provider。
- Google Drive / Confluence connector 可把文档写入指定 `tenant_id + kb_id`。
- `Settings.knowledge_base.default_kb_id` 默认是 `"global"`。

缺口在于 agent 运行时缺少“可见 KB 范围”的统一解析入口。这个逻辑不应该散落在 long-term-ctx、agent-runtime 或 connector 中。

## Binding Model

绑定关系存储在 SQLite 中，而不是 `settings.yaml`。

原因：

- agent 到 KB 的关系可能随运行环境和试用反馈调整，不适合作为部署期静态配置。
- Pilot 期间可能需要通过 CLI / 后续 Admin API 调整绑定。
- 绑定属于运行时业务状态，和 connector sync state 更接近。

表结构建议：

```sql
knowledge_base_agent_bindings (
  tenant_id  TEXT NOT NULL,
  agent_id   TEXT NOT NULL,
  kb_id      TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (tenant_id, agent_id, kb_id)
)
```

不强制外键依赖 `knowledge_bases`。允许先绑定一个暂不存在的 `kb_id`，后续再通过 connector 或手动 ingest 创建内容。

## Public API

建议 public API：

```python
@dataclass(frozen=True)
class AgentKnowledgeBaseBinding:
    tenant_id: str
    agent_id: str
    kb_id: str
    created_at: datetime


def bind_agent_to_kb(tenant_id: str, agent_id: str, kb_id: str) -> AgentKnowledgeBaseBinding:
    """绑定 agent 到一个 KB；重复绑定幂等。"""


def unbind_agent_from_kb(tenant_id: str, agent_id: str, kb_id: str) -> None:
    """解除绑定；不存在时幂等。"""


def list_agent_kb_bindings(tenant_id: str, agent_id: str) -> list[AgentKnowledgeBaseBinding]:
    """列出 agent 的显式 KB 绑定。"""


def resolve_agent_kb_ids(tenant_id: str, agent_id: str) -> list[str]:
    """解析 agent 的有效 KB 范围。"""
```

`resolve_agent_kb_ids()` 是跨模块唯一推荐入口。long-term-ctx 不应直接读 binding 表。

## Resolution Rules

解析规则：

1. 查询 `knowledge_base_agent_bindings`。
2. 如果存在显式绑定，按稳定顺序返回绑定的 `kb_id`。
3. 如果不存在显式绑定，读取 `Settings.knowledge_base.default_kb_id`。
4. 如果默认 KB 已配置，则返回 `[default_kb_id]`。
5. 如果默认 KB 未配置、为空或解析后不可用，则返回空列表。

是否检查默认 KB 存在，可以在实现阶段选择：

- MVP 可只检查配置是否为空，把“不存在”交给 `knowledge_base.search()` 返回空结果。
- 如果已有轻量 KB existence helper，可以检查并记录更准确诊断。

无论哪种实现，缺默认 KB 都不能阻断 agent 对话。

## Long-Term Context Integration

long-term-ctx 的 built-in knowledge provider 应调整为：

1. 使用当前 `tenant_id` 和 `agent_id` 调用 `resolve_agent_kb_ids()`。
2. 如果返回空列表，跳过 `knowledge_base.search()`。
3. 如果返回 KB 列表，调用 `knowledge_base.search(query, tenant_id, kb_ids, ...)`。
4. KB 无结果时保持现有降级语义：memory 仍可正常注入，agent 仍可回答。

这个 change 不改变 memory 和 KB 的预算策略，只改变 KB 候选来源范围。

## Diagnostics

默认 KB 缺失或解析结果为空时，应记录可诊断事件，例如：

- `knowledge_base.default_missing`
- `knowledge_base.agent_kb_scope_empty`

诊断事件不能包含 secret，也不能写入完整 query 或文档内容。至少包含：

- `tenant_id`
- `agent_id`
- `reason`

实现阶段可以选择 structured logger 或 trace event；如果发生在一次 agent run 中，优先使用 observability trace event，方便后续排障。

## Error Handling

- 重复绑定：幂等返回现有绑定或等价结果。
- 解除不存在绑定：幂等成功。
- 空 `tenant_id`、`agent_id` 或 `kb_id`：fail fast。
- 绑定暂不存在的 KB：允许。
- `knowledge_base.search()` 对不存在或无内容 KB 返回空结果，不把它视为绑定错误。

## Testing

测试重点：

- binding API 可从 `fleetent.intelligence.knowledge_base` public API 导入。
- 重复绑定幂等。
- unbind 幂等。
- tenant 隔离。
- agent 隔离。
- 显式绑定覆盖默认 KB。
- 未绑定时返回默认 KB。
- 默认 KB 缺失时返回空列表并记录诊断。
- long-term-ctx 调用 `resolve_agent_kb_ids()`，并把返回的 KB 列表传给 `knowledge_base.search()`。
- 空 KB 范围时 long-term-ctx 不调用 `knowledge_base.search()`，agent 上下文正常降级。

## Non-Goals

本 change 不解决：

- UI 绑定管理。
- HTTP admin endpoint。
- 文档级权限。
- 用户到 Google Drive / Confluence ACL 的实时映射。
- 多级组织继承策略。
- Shared Memory。
- query planner / graph search / rerank 策略。
