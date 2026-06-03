# Tasks

## 1. Overflow menu + Deploy action

- [x] 1.1 Write failing UI tests: renderAgents uses a `⋯` overflow menu (actions-menu); menu still references all actions + IS_VIEWER gate; agDeploy function + deploy dialog + channel-binding endpoint present
- [x] 1.2 Implement overflow menu in renderAgents (details/summary dropdown) + CSS; add Deploy menu item, ag-deploy-modal, and agDeploy/agDoDeploy posting the channel binding

## 2. Gate

- [x] 2.1 ruff format + check, mypy, full `uv run pytest -x -q`
