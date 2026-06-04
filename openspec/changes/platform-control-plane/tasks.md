## 1. Platform boots agent-free (control plane)

- [ ] 1.1 Write failing test: platform app starts with no agent home and no IM tokens;
  `/health` + `/admin/*` work; no IM connector/loop/sandbox started (spy the connector
  manager + slack supervisor are not invoked).
- [ ] 1.2 Prune the platform lifespan: drop `start_all_enabled`,
  `_slack_supervisor.start_from_index`, agent-use MCP/sandbox/session bring-up. Keep
  admin routers, health, auth, builtin-admin seed, platform cron. Make 1.1 green.

## 2. Remove execution endpoints from the platform

- [ ] 2.1 Write failing test: POST `/chat`, `/ws`, `/webhook/*` on the platform app
  return 404.
- [ ] 2.2 Remove the `/chat`, `/ws`, `/webhook` routes from the platform app. Make 2.1
  green.

## 3. Migrate + closeout

- [ ] 3.1 Split server tests: platform-side keeps control-plane assertions; move
  execution/IM tests to the agent-runtime suite (or mark them agent-runtime-scoped).
- [ ] 3.2 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [ ] 3.3 Full suite `uv run pytest -x -q` green.
