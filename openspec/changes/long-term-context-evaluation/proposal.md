## Why

`long-term-context-foundation` has a working memory / knowledge retrieval and prompt injection
path, but current tests mostly prove mechanics: providers are called, sections are formatted, and
budget pressure omits low-priority content. They do not give maintainers a stable way to judge
whether long-term context injection quality regresses across memory, KB, and runtime changes.

This change adds a deterministic evaluation baseline for long-term context. The goal is to make
context injection observable in tests without requiring a real LLM, real embedding provider, or
external knowledge source by default.

## What Changes

- Add `tests/evaluation/` fixtures for long-term context injection scenarios.
- Add a long-term context evaluation runner that:
  - loads explicit fixture cases
  - patches memory and knowledge providers with deterministic fake results
  - calls `build_context(user_id, query, agent_id, available_tokens)`
  - asserts expected snippets and sources are injected
  - asserts forbidden snippets and sources are omitted
  - records whether budget pressure produced expected omissions
- Cover at least these baseline cases:
  - memory-only personal preference injection
  - KB-only factual reference injection
  - combined memory and KB injection
  - zero or insufficient token budget omission
  - optional knowledge provider disabled / empty behavior
- Keep default evaluation isolated from `data/`, real SaaS, real LLM, and real embedding services.
- Add an optional manual smoke path only if future real-provider configuration is explicitly enabled;
  by default the real-provider case must skip.
- Update long-term context docs and CI quality gate spec language so this evaluation remains
  manually runnable and outside the default PR gate.

## Out of Scope

- No LLM-graded answer-quality evaluation.
- No production ranking metrics dashboard.
- No budget policy redesign; `long-term-context-budget-policy` owns policy changes.
- No automatic memory writes, deletion, compaction, or reflection maintenance.
- No real SaaS connector, real KB sync, or real embedding provider in default tests.
- No new persistent tables or migrations.

## Dependencies

- Requires `long-term-context-foundation`.
- Benefits from existing memory extraction and KB retrieval evaluations, but does not replace them.
- Must complete before `long-term-context-budget-policy` can claim effect improvements.

## Module Boundary Impact

- **Owning package**: no production owning package; this change belongs to long-term context
  evaluation test ownership under `tests/evaluation`.
- **Public API surface**: no new production public API. The evaluation runner uses existing
  `fleetent.intelligence.long_term_ctx.build_context()`, `BuiltContext`, and `ContextSource`.
- **Owned tables**: none.
- **Config namespace**: no production config. Optional real-provider smoke uses explicit
  `FLEETENT_EVAL_*` environment variables only.
- **Cross-module dependencies**: tests patch memory-layer search and long-term context knowledge
  provider through public/imported boundaries; they do not call private KB connector internals.
- **Migration / shim plan**: none.

## Impact

- **Code**: evaluation helper and tests only unless the evaluation exposes an existing contract bug.
- **Tests**: new deterministic evaluation fixtures and pytest coverage in `tests/evaluation/`.
- **CI**: no default PR/main gate change; evaluation stays manually runnable.
- **Data**: no real user data and no writes under `data/`.
