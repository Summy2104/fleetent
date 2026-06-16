# Tasks

> C5：纯减法 BREAKING。前置 C3 已 apply 落 main（reconcile 替代启停）。无管理库迁移。**严格只删 controller/start-stop/runtime-status + 死函数，不碰 agent-lifecycle-toggle(enable/disable/archive) 与 materialize。** 收尾判据对照 main 基线"无新增失败"。

## 1. 删除前确认调用方（防漏网/防 BREAKING 失联）

- [ ] 1.1 grep 确认 `/start`、`/stop`、`/runtime-status` 的调用方：`grep -rn "agents/.*/start\|agents/.*/stop\|runtime-status" src tests static`——UI(`admin.html`)/脚本若有调用，本 change 一并改（改为 status 切换 + 读 node 上报）或在收尾说明
- [ ] 1.2 grep 确认 `agent_routing_status` 仍零生产调用（仅测试引用）

## 2. 删 lifecycle_admin_api（start/stop/runtime-status）

- [ ] 2.1 调整测试：删 `tests/integration/test_lifecycle_admin_api.py`；`uv run pytest tests/integration/test_lifecycle_admin_api.py -q` 应消失/不再收集（见红→删后绿）
- [ ] 2.2 删 `src/fleetent/platform/agent_lifecycle/lifecycle_admin_api.py`；去 `server.py:36` import 与 `:301` `include_router`
- [ ] 2.3 跑受影响 server 测试，确认无新增失败

## 3. 删 AgentController

- [ ] 3.1 调整测试：删 `tests/unit/test_agent_controller.py`；`test_lifecycle_logging.py` 仅删其 controller/api 用例（若整文件仅测这俩则整删），materialize 日志用例保留
- [ ] 3.2 删 `src/fleetent/platform/agent_lifecycle/controller.py`
- [ ] 3.3 跑受影响测试见绿

## 4. 删死函数 agent_routing_status

- [ ] 4.1 调整测试：删 `test_platform_admin_api_unit.py` 的 agent_routing_status 用例(行~990/996)、`test_server_lifespan_and_wiring.py` 的 monkeypatch(行~250)、`test_agent_identity_phase3_routes.py`（若整文件仅测此函数则整删，否则删相关用例）
- [ ] 4.2 删 `server.py` 的 `agent_routing_status`（~460）
- [ ] 4.3 跑受影响测试见绿

## 5. spec deltas（已随 propose 写好，apply 时核对）

- [ ] 5.1 确认 `specs/platform-agent-lifecycle/spec.md`（REMOVED start/stop）与 `specs/agent-lifecycle-logging/spec.md`（REMOVED controller/api 两条）与实际删除一致；archive 时同步主 specs

## 6. 收尾验证

- [ ] 6.1 确认 **agent-lifecycle-toggle 未被动**（enable/disable/archive store+API 仍在）：`grep -rn "def enable\|def disable\|def archive" src/fleetent/platform/agent_management_console`
- [ ] 6.2 确认 materialize 未被动（platform-agent-lifecycle 物化需求保留）
- [ ] 6.3 `make test-pr` 全绿
- [ ] 6.4 `make test-unit-ci`（覆盖率关 `--fail-under=76`）通过——删代码通常抬升覆盖，注意别删了测试却留无覆盖代码
- [ ] 6.5 `uv run pytest tests/integration -q`（对照 main 基线无新增失败）
- [ ] 6.6 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过
- [ ] 6.7 `git grep -n "lifecycle_admin_api\|AgentController\|agent_routing_status"` 仅剩归档/历史文档类残留（src/tests 应净空）
- [ ] 6.8 `openspec validate retire-inmemory-controller` 通过
