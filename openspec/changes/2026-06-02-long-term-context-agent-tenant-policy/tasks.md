# tasks

## 1. OpenSpec proposal

- [ ] 1.1 Create proposal, design, tasks, and long-term-ctx spec delta
- [ ] 1.2 Run `openspec validate 2026-06-02-long-term-context-agent-tenant-policy --strict`

## 2. Policy model and persistence

- [ ] 2.1 Write failing tests: Alembic creates `long_term_context_policies` with tenant/agent/source/budget fields
- [ ] 2.2 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 2.3 Implement migration and store boundary with named parameters
- [ ] 2.4 Verify green: run `uv run pytest tests/integration -x -q`
- [ ] 2.5 Write failing tests: invalid source, empty tenant_id, invalid budget/top_k fail fast
- [ ] 2.6 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 2.7 Implement validation
- [ ] 2.8 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Policy resolution

- [ ] 3.1 Write failing tests: no policy preserves current User Memory + KB behavior and leaves Shared Memory disabled
- [ ] 3.2 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 3.3 Implement default policy resolution
- [ ] 3.4 Verify green: run `uv run pytest tests/unit -x -q`
- [ ] 3.5 Write failing tests: agent policy overrides tenant policy for matching source
- [ ] 3.6 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 3.7 Implement override resolution
- [ ] 3.8 Verify green: run `uv run pytest tests/unit -x -q`

## 4. Policy-aware context building

- [ ] 4.1 Write failing tests: explicit Shared Memory policy calls `search_shared_memory()` and records shared source attribution
- [ ] 4.2 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 4.3 Implement Shared Memory provider integration
- [ ] 4.4 Verify green: run `uv run pytest tests/unit -x -q`
- [ ] 4.5 Write failing tests: disabled source is not queried and budget decisions explain exclusion
- [ ] 4.6 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 4.7 Implement source enablement and budget decision metadata
- [ ] 4.8 Verify green: run `uv run pytest tests/unit -x -q`

## 5. Evaluation and docs

- [ ] 5.1 Write failing tests: deterministic evaluation covers tenant default, agent override, and Shared Memory disabled-by-default
- [ ] 5.2 Verify red: run `uv run pytest tests/evaluation -x -q`
- [ ] 5.3 Implement evaluation fixture/runner
- [ ] 5.4 Verify green: run `uv run pytest tests/evaluation -x -q`
- [ ] 5.5 Update `docs/capabilities/long-term-ctx.md`, `docs/capabilities/memory.md`, and owner roadmap

## 6. Verification

- [ ] 6.1 Run `uv run ruff format src tests`
- [ ] 6.2 Run `uv run ruff check src tests`
- [ ] 6.3 Run `uv run mypy src`
- [ ] 6.4 Run `uv run pytest -x -q`
- [ ] 6.5 Run `openspec validate 2026-06-02-long-term-context-agent-tenant-policy --strict`
- [ ] 6.6 Run `git diff --check`
