# Design

## Evaluation Result

可以进入设计。依据：

- long-term-ctx 已有 `BuiltContext`、`BudgetMetadata`、`BudgetDecision` 和 deterministic budget policy。
- KB 已有 tenant + agent binding public API。
- Shared Memory 已有 team / tenant scope、search API、vector namespace 和 reindex iterator。
- 当前 docs 明确 Shared Memory 不接 prompt 注入，因此第一版 policy 可以默认 disabled，避免行为突变。
- 当前 `agent_store.Agent` 仍未包含 `tenant_id` / `team_id`，因此本 spec 需要把 agent 归属作为前置/配套变更写清楚。

## Agent Ownership

Shared Memory scope 不应在 long-term context policy 中任意手写。第一版采用 agent 归属解析：

- agent 必须有 `tenant_id`，默认 backfill 为 `"default"`。
- agent 可选有 `team_id`。
- tenant-level Shared Memory scope 固定解析为 `shared:tenant:{agent.tenant_id}`。
- team-level Shared Memory scope 固定解析为 `shared:team:{agent.team_id}`，且只有 `team_id` 非空时可用。
- 不支持跨 tenant / 跨 team 访问；未来如需要，单独增加 `agent_shared_memory_grants` 或 governance spec。

agent 归属更像 agent identity / ownership，不是 prompt version 的一部分；推荐放在 agent 主表或 agent runtime
identity 边界，而不是 agent version 快照。若后续 agent management 采用 versioned definition，version 可读取归属，
但不应让 prompt version 切换改变 tenant/team ownership。

## Policy Model

`long_term_context_policies`：

- `id`
- `tenant_id`
- `agent_id` nullable
- `user_memory_enabled`
- `tenant_shared_memory_enabled`
- `team_shared_memory_enabled`
- `knowledge_base_enabled`
- per-source `max_tokens` / `top_k` fields：`user_memory_max_tokens`、`tenant_shared_memory_max_tokens`、
  `team_shared_memory_max_tokens`、`knowledge_base_max_tokens` 等
- `conflict_preference`
- `created_at`
- `updated_at`

Tenant default row applies first; agent row overrides the same tenant's defaults.

## Resolution Rules

- If no policy rows exist, preserve current behavior:
  - User Memory enabled;
  - Knowledge Base enabled via existing KB binding/default KB rules;
  - Shared Memory disabled.
- Agent policy overrides tenant policy for the same tenant and agent.
- Tenant Shared Memory requires `tenant_shared_memory_enabled=True` and uses agent.tenant_id.
- Team Shared Memory requires `team_shared_memory_enabled=True` and non-empty agent.team_id.
- Policy cannot name arbitrary Shared Memory scopes.
- Budget decisions include source type and policy reason.

## Public API Shape

```python
@dataclass(frozen=True)
class AgentContextIdentity:
    agent_id: str
    tenant_id: str
    team_id: str | None


@dataclass(frozen=True)
class ContextPolicySourceBudget:
    source: Literal["user_memory", "tenant_shared_memory", "team_shared_memory", "knowledge_base"]
    enabled: bool
    max_tokens: int
    top_k: int
    priority: int


@dataclass(frozen=True)
class ContextPolicy:
    tenant_id: str
    agent_id: str
    agent_team_id: str | None
    sources: list[ContextPolicySourceBudget]


def resolve_context_policy(agent: AgentContextIdentity) -> ContextPolicy:
    ...
```

Implementation can either extend `build_context()` to resolve policy internally or introduce
`build_context_with_policy()` as an intermediate API. The final design should keep current callers compatible.

## Open Questions

- Agent team ownership source must be added to agent management. First implementation should add `tenant_id` / `team_id` to the agent boundary if it is still absent.
- Should policy rows use one wide row or per-source rows? This design recommends one wide row for easier admin editing and to avoid arbitrary scope grants.
- Product UI for policy editing remains out of scope.
