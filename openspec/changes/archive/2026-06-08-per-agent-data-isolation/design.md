## Context

Each `fleetent agent run <id>` process is a self-contained standalone agent. The agent's
config (`agent.yaml`, `.env`) already lives under `agents/<id>/`, but all runtime data
(sessions, DB, logs, diagnostics, IM approvals) shares a single `FLEETENT_HOME/data/`
directory. `agent_app.boot()` already knows `home_dir = FLEETENT_HOME/agents/<id>/`
as its first computation — the missing step is redirecting data sinks to `home_dir/data/`
before any infrastructure initialises.

Relevant modules and their data paths (all module-level constants set at import time):
- `session/manager.py`: `SESSIONS_DIR = paths.sessions_dir()` → `data/sessions/`
- `db.py`: default `DATABASE_URL = sqlite:///data/fleetent.db`
- `im_gateway/access.py`: `APPROVALS_PATH` → `data/im_approvals.json`
- `observability/diagnostics.py`: `_default_data_dir()` → `data/`
- `observability/structured_logging.py`: log directory defaults to `data/logs/`; already
  overridable via `configure_structured_logging(directory=...)`

The codebase already uses the pattern of monkeypatching module-level constants for test
isolation (`monkeypatch.setattr(session_mgr, "SESSIONS_DIR", ...)`). The same mechanism
is used in production code to redirect paths (e.g. `agent_app` redirects `skills` scan).

## Goals / Non-Goals

**Goals**
- Each standalone agent process writes all runtime data exclusively to `home_dir/data/`
- `paths.agent_data_dir(agent_id)` formalises the per-agent data path in the central resolver
- No new environment variables; no changes to `FLEETENT_HOME` semantics
- Existing test isolation (monkeypatch of module constants) continues to work unchanged

**Non-Goals**
- Automatic migration of existing `FLEETENT_HOME/data/` contents to per-agent dirs
- Platform multi-agent mode data isolation (platform runs no agents in-process)
- Per-agent `users.db` isolation (platform data, not agent data)

## Decisions

**D1 — Redirect in `boot()` via direct attribute assignment, not new env vars**

`boot()` computes `home_dir` before any DB/session init. At that point we directly assign:
```python
session_mgr.SESSIONS_DIR = home_dir / "data" / "sessions"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{home_dir / 'data' / 'fleetent.db'}")
access_module.APPROVALS_PATH = home_dir / "data" / "im_approvals.json"
```
Alternative considered: introduce `FLEETENT_AGENT_HOME` env var and modify `paths.data_dir()`
to check it. Rejected: adds env-var surface area and makes `paths.py` context-dependent.
Direct assignment in `boot()` is already the established pattern (`scan_skills` does the
same for `skills_dir`).

**D2 — `DATABASE_URL` via `os.environ.setdefault`, not `db.py` patching**

`db.py` reads `DATABASE_URL` env var at the point it initialises the engine. Setting the
env var before `_start_infra()` (which triggers DB init) is sufficient. `setdefault` ensures
a user's explicit `DATABASE_URL=...` in `.env` always wins.

**D3 — Log directory: resolve blank `observability.logging.directory` to `home_dir/data/logs/`**

`_configure_logging_from_agent()` already receives the log directory from `agent.observability
.logging.directory`. Changing the default in `ObservabilitySettings` from `"data/logs"` (a
CWD-relative string) to `""` (blank), then resolving blank → `home_dir/data/logs/` in
`_configure_logging_from_agent()`, keeps the config schema clean and makes the resolution
explicit in one place. Existing `agent.yaml` files with `directory: data/logs` keep working
(treated as a CWD-relative override, which is how they behave today).

**D4 — `paths.agent_data_dir(agent_id)` added to `paths.py` for formalisation**

Makes the per-agent data path derivation canonical and inspectable in tests. Other modules
do not import it directly; `boot()` uses `home_dir / "data"` inline (same value).

## Risks / Trade-offs

- **Existing deployed data not migrated** → Operators starting the agent after this change
  will have a clean `agents/<id>/data/`; historical data stays in `FLEETENT_HOME/data/`.
  Sessions won't resume from the old path. Mitigation: document in release notes; provide
  a manual `mv` command.
- **`DATABASE_URL` in `.env` wins over per-agent default** → If an operator set a shared
  `DATABASE_URL` in `FLEETENT_HOME/.env` or system env, it overrides the per-agent default
  (`setdefault` is a no-op). This is intentional (explicit config > convention), but
  operators using a shared `.env` must update it per-agent.

## Migration Plan

1. Deploy new binary.
2. Stop each agent process.
3. `mkdir -p ~/.fleetent/agents/<id>/data && mv ~/.fleetent/data/{sessions,fleetent.db,im_approvals.json,logs,diagnostics} ~/.fleetent/agents/<id>/data/` (optional — skip for a clean start).
4. Restart agent.

Rollback: revert binary, data at `FLEETENT_HOME/data/` is untouched if migration was skipped.

## Open Questions

None — design is fully resolved based on code analysis.
