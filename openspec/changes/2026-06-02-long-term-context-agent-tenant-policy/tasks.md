# tasks

## 1. OpenSpec proposal

- [x] 1.1 Create proposal, design, tasks, and long-term-ctx spec delta
- [x] 1.2 Run `openspec validate 2026-06-02-long-term-context-agent-tenant-policy --strict`

## 2. Policy model and persistence

- [x] 2.1 Write failing tests: agent boundary exposes `tenant_id` and optional `team_id`; existing agents backfill `tenant_id="default"`
- [x] 2.2 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 2.3 Implement agent ownership migration / store boundary or wire to existing agent management public API
- [x] 2.4 Verify green: run `uv run pytest tests/integration -x -q`
- [x] 2.5 Write failing tests: Alembic creates `long_term_context_policies` with tenant default + agent override fields for source enablement and budgets
- [x] 2.6 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 2.7 Implement policy migration/store boundary with named parameters
- [x] 2.8 Verify green: run `uv run pytest tests/unit -x -q`
- [x] 2.9 Write failing tests: empty tenant_id, invalid budget/top_k, and arbitrary Shared Memory scope grants fail fast
- [x] 2.10 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 2.11 Implement validation
- [x] 2.12 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Policy resolution

- [x] 3.1 Write failing tests: no policy preserves current User Memory + KB behavior and leaves Shared Memory disabled
- [x] 3.2 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement default policy resolution
- [x] 3.4 Verify green: run `uv run pytest tests/unit -x -q`
- [x] 3.5 Write failing tests: agent policy overrides tenant policy for the same tenant and agent
- [x] 3.6 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 3.7 Implement override resolution
- [x] 3.8 Verify green: run `uv run pytest tests/unit -x -q`

## 4. Policy-aware context building

- [x] 4.1 Write failing tests: enabled tenant Shared Memory calls `search_shared_memory("tenant", agent.tenant_id, ...)` and records shared source attribution
- [x] 4.2 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 4.3 Implement tenant Shared Memory provider integration
- [x] 4.4 Verify green: run `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing tests: enabled team Shared Memory calls `search_shared_memory("team", agent.team_id, ...)`; empty team_id skips with budget decision
- [x] 4.6 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 4.7 Implement team Shared Memory provider integration and skip reason
- [x] 4.8 Verify green: run `uv run pytest tests/unit -x -q`
- [x] 4.9 Write failing tests: disabled source is not queried and budget decisions explain exclusion
- [x] 4.10 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 4.11 Implement source enablement and budget decision metadata
- [x] 4.12 Verify green: run `uv run pytest tests/unit -x -q`

## 5. Evaluation and docs

- [ ] 5.1 Write failing tests: deterministic evaluation covers tenant default, agent override, Shared Memory disabled-by-default, and no cross-team/tenant access
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
