## Context

Long-term context is the integration point where memory and knowledge-base retrieval influence the
agent prompt. Unit and integration tests already cover the public API and provider mechanics, but
they are not structured as reusable evaluation fixtures. That makes it hard to add cases that
describe expected and forbidden prompt context over time.

This design intentionally keeps the first evaluation deterministic. It evaluates whether the
context builder injects the right snippets and source summaries for controlled inputs. It does not
score final model answers, because that would require a real LLM or evaluator and would make the
default test path unstable.

## Fixture Format

Each fixture case is a JSON document with explicit inputs and assertions:

- `name`: stable case identifier.
- `user_id`, `agent_id`, `query`, `available_tokens`: arguments passed to `build_context()`.
- `memories`: fake memory results, including `id`, `type`, `content`, and optional timestamps.
- `knowledge`: fake knowledge results, including `id`, `content`, `score`, and metadata.
- `expected_text`: snippets that must appear in `BuiltContext.text`.
- `forbidden_text`: snippets that must not appear in `BuiltContext.text`.
- `expected_sources`: source ids/types that must appear in `BuiltContext.sources`.
- `forbidden_sources`: source ids/types that must not appear in `BuiltContext.sources`.

The runner fails fast when required fields are missing or source assertions are malformed. Fixtures
must be small and self-contained so failures are readable.

## Runner

The evaluation runner loads fixtures from `tests/evaluation/fixtures/long_term_context/`.
For each case, it patches:

- `memory_layer.search()` with deterministic fake `MemoryItem` results.
- `long_term_ctx.set_knowledge_provider()` with a deterministic async fake provider.

It then calls `build_context()` and validates text/source expectations. After each case, it resets
the knowledge provider to avoid cross-test state.

The runner uses no SQLite database by default because `build_context()` only needs provider output
for these cases. If future cases need store-backed setup, they must use `tmp_path` and never write
under `data/`.

## Optional Real Provider Smoke

The default evaluation must not call external services. A real-provider smoke test may exist only
behind explicit environment variables such as `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1`. If enabled
but credentials or provider configuration are absent, the test must skip instead of failing.

The real-provider smoke is not a quality gate. It is a manual operator/developer tool for provider
changes.

## Error Handling

Invalid fixture schema raises a dedicated validation error so fixture problems are separated from
runtime behavior regressions.

Provider failures are not the primary target of this change. The deterministic fixtures should
focus on injection behavior: expected snippets/sources, forbidden snippets/sources, and budget
omissions.

## Testing

Tests follow the project TDD gate:

- Fixture schema tests fail before loader implementation.
- Runner behavior tests fail before deterministic provider wiring.
- Scenario tests fail before fixtures are accepted as passing baseline.
- Real-provider smoke skip behavior fails before opt-in guard implementation.

The relevant loop command is `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`.
Final verification uses the full project quality gates required by the project workflow.
