## 1. Two-level navigation refactor

- [x] 1.1 Write failing test: admin.html has grouped nav (groups Access / Agents & Skills / Models & Connectors / Ops / Audit) and existing 5 tabs still reachable (tests/integration/test_admin_console_ui.py)
- [x] 1.2 Refactor nav to group bar + per-group tab row (`switchGroup` + `switchTab`), regroup existing Users/IM/Connectors/KB/Audit without regressing; run pytest → green
- [x] 1.3 Browser-verify existing tabs still load after refactor

## 2. Skills module

- [x] 2.1 Write failing UI tests: Skills tab, list wiring `GET /admin/skills`, actions (create/edit/enable/disable/reload/delete/restore/bind agents/force-publish/observability/provenance), proposals review (diff/approve/reject), viewer-hidden write controls
- [x] 2.2 Add Skills section + JS (`sk*`) wiring all `/admin/skills` endpoints; admin-gate writes; run pytest → green
- [x] 2.3 Browser-verify Skills tab: list renders, an action POSTs correct path, proposal approve works

## 3. Model Providers module

- [x] 3.1 Write failing UI tests: Providers tab, list `GET /admin/providers` masked, CRUD + connectivity-test + pricing + observability + routes(GET/PUT/preview) + health, viewer-hidden writes
- [x] 3.2 Add Providers section + JS (`pv*`); secret fields password/no-prefill; run pytest → green
- [x] 3.3 Browser-verify Providers tab: list masked, connectivity-test + route update POST correct paths

## 4. Agents module

- [x] 4.1 Write failing UI tests: Agents tab, list `GET /admin/agents` + templates, lifecycle (enable/disable/archive/restore/clone), observability, versions (list/activate), bindings (users/channels), viewer-hidden writes
- [x] 4.2 Add Agents section + JS (`ag*`); run pytest → green
- [x] 4.3 Browser-verify Agents tab: list renders, clone + version activate + bind POST correct paths

## 5. Statistics module

- [x] 5.1 Write failing UI tests: Statistics tab, per-user `GET /admin/stats/per-user`, agent overview/compare/tools, user requests + request detail + session trace, export + reports
- [x] 5.2 Add Statistics section + JS (`st*`); run pytest → green
- [x] 5.3 Browser-verify Statistics tab: per-user renders, trace open + export trigger correct paths

## 6. Monitoring + Alerts module

- [x] 6.1 Write failing UI tests: Monitoring tab metrics `GET /admin/monitoring/metrics`, alert rules CRUD (list/create/disable/delete), alerts (list/ack/silence/maintenance), viewer-hidden writes
- [x] 6.2 Add Monitoring section + JS (`mon*`); destructive actions confirm; run pytest → green
- [x] 6.3 Browser-verify Monitoring tab: metrics render, rule create + alert ack correct paths

## 7. Sessions module

- [x] 7.1 Write failing UI tests: Sessions tab list `GET /admin/sessions`, controls (takeover/release/inject/force-end/clear/reset/bulk), chat playground (start/message/pin/export), viewer-hidden controls
- [x] 7.2 Add Sessions section + JS (`sess*`); destructive actions confirm; stream degraded to non-stream message per design; run pytest → green
- [x] 7.3 Browser-verify Sessions tab: list renders, takeover + force-end (confirmed) + playground message correct paths

## 8. OAuth Connectors + MCP module

- [x] 8.1 Write failing UI tests: OAuth Connectors tab (distinct from IM Connectors), connectors list `GET /admin/connectors` masked + CRUD/lifecycle, grants matrix + revoke + offboarding, MCP doctor/servers/tools/reconnect, viewer-hidden writes
- [x] 8.2 Add OAuth+MCP section + JS (`oc*`/`mcp*`); secret masked/no-prefill; run pytest → green
- [x] 8.3 Browser-verify tab: connectors masked, grant revoke + mcp reconnect correct paths

## 9. AskIt module

- [x] 9.1 Write failing UI tests: AskIt tab series `GET /admin/askit/series` + tasks list, run + task detail; stream degraded per design
- [x] 9.2 Add AskIt section + JS (`ak*`); run pytest → green
- [x] 9.3 Browser-verify AskIt tab: series/tasks render, run + task detail correct paths

## 10. Gates

- [x] 10.1 `uv run ruff format src tests && uv run ruff check src tests`
- [x] 10.2 `uv run mypy src`
- [x] 10.3 Full `uv run pytest -q` green
- [x] 10.4 Browser smoke: every group/tab loads without console error
