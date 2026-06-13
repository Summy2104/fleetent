# 2026-06-13: Descope Dormant Long-Term Context Policy

## Context

The dormant management-db policy table and its companion long-term-context policy module
modeled tenant-default and agent-override source selection, including a Shared Memory
gate. The whole path had tests and storage, but no production caller: live long-term
context assembly already runs through `build_context()` and the budget-only
`_resolve_policy()` path in `__init__.py`.

## Decision

- Remove the dormant management-db table, module, public exports, and tests instead of
  leaving a partial stub.
- Keep the active budget-policy path unchanged: `build_context`, `_resolve_policy`,
  `BudgetPolicy`, `ContextSource`, and `BuiltContext` remain the live API.
- Descope the unused "Shared Memory enters long-term context via policy" design with this
  change; Shared Memory storage and read APIs stay intact, but prompt injection via that
  dormant path is no longer described as an available capability.

## Consequences

- Management-db schema loses an unused table and the surrounding API surface disappears.
- Long-term context behavior stays on the existing memory + knowledge budget flow, with
  regression coverage proving it still assembles prompt context after the removal.
- If Shared Memory prompt injection is needed later, it should be redesigned from current
  requirements rather than recovered from half-wired historical code.
