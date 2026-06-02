# Design

## Evaluation Result

可以进入设计。依据：

- long-term-ctx 已有 `BuiltContext`、`BudgetMetadata`、`BudgetDecision` 和 deterministic budget policy。
- KB 已有 tenant + agent binding public API。
- Shared Memory 已有 team / tenant scope、search API、vector namespace 和 reindex iterator。
- 当前 docs 明确 Shared Memory 不接 prompt 注入，因此第一版 policy 可以默认 disabled，避免行为突变。

## Policy Model

`long_term_context_policies`：

- `id`
- `tenant_id`
- `agent_id` nullable
- `source`：`user_memory`、`shared_memory`、`knowledge_base`
- `enabled`
- `max_tokens`
- `top_k`
- `priority`
- `scope_type` nullable（Shared Memory 用 `tenant` 或 `team`）
- `scope_id` nullable
- `created_at`
- `updated_at`

Tenant default rows apply first; agent rows override matching source.

## Resolution Rules

- If no policy rows exist, preserve current behavior:
  - User Memory enabled;
  - Knowledge Base enabled via existing KB binding/default KB rules;
  - Shared Memory disabled.
- Agent policy overrides tenant policy for the same source.
- Shared Memory requires explicit enabled policy and explicit scope.
- Unknown source is rejected at write time.
- Budget decisions include source type and policy reason.

## Public API Shape

```python
@dataclass(frozen=True)
class ContextPolicySourceBudget:
    source: Literal["user_memory", "shared_memory", "knowledge_base"]
    enabled: bool
    max_tokens: int
    top_k: int
    priority: int
    scope_type: str | None = None
    scope_id: str | None = None


@dataclass(frozen=True)
class ContextPolicy:
    tenant_id: str
    agent_id: str
    sources: list[ContextPolicySourceBudget]


def resolve_context_policy(tenant_id: str, agent_id: str) -> ContextPolicy:
    ...
```

Implementation can either extend `build_context()` to resolve policy internally or introduce
`build_context_with_policy()` as an intermediate API. The final design should keep current callers compatible.

## Open Questions

- Who owns team-to-agent mapping for Shared Memory `team` scopes? First implementation can require explicit `scope_id` in policy and avoid deriving it.
- Should tenant policies be stored in SQLite or config? This design recommends SQLite because admin policy changes should not require restart.
- Product UI for policy editing remains out of scope.
