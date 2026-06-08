## 1. agent_init — FLEETENT_TUI_TOKEN generation

- [x] 1.1 Write failing tests: `scaffold_agent_home()` writes `FLEETENT_TUI_TOKEN=ma-...` to `.env`; value is non-empty and starts with `ma-`
- [x] 1.2 Update `scaffold_agent_home()` in `agent_init.py` to append `FLEETENT_TUI_TOKEN=ma-<token_hex(32)>` to `.env`

## 2. agent_app — /ws token-based auth

- [x] 2.1 Write failing tests: `/ws` accepts connection when `FLEETENT_TUI_TOKEN` matches; rejects with 1008 on mismatch; rejects when env var not set
- [x] 2.2 Replace `user_store.authenticate()` in `agent_app.build_app()` `/ws` endpoint with `FLEETENT_TUI_TOKEN` env var check; `user_id="local"` on success

## 3. Full test suite green

- [x] 3.1 Run `uv run pytest -x -q` and fix any regressions
