## 1. 探针：spawned route server 能否真 apply DB-seeded 提案

- [ ] 1.1 **探针**：用 `managed_reflection_stack` seed 一条 memory mark_stale 提案（现有 `seed_memory_stale_proposal`），经 `_im_helpers.managed_agent_route_server(stack)` 起的 route server POST `/im/route` 发 `approve <id>`，观测 agent 侧 `agent_state.db` 的 `reflection_proposals.status` 是否真转 `applied`。确认跨进程（route server 进程 resolve+apply、node agent 进程并发持库）无锁问题、状态真生效。记录结论；若 DB-seeded 提案需原进程 resolve 才生效，据实调整审批驱动方式并在 design 注明。

## 2. memory 提案 approve→apply 真跑（去 skip）

- [ ] 2.1 **测试（红）**：把 `test_memory_mark_stale_proposal_can_be_approved_via_im_route` 的断言改为真执行（不再走会 skip 的 `_new_agent_gateway_port` 路径）。在 helper 改好前跑——应见红（skip 或失败），证明当前实现未覆盖目标行为。最窄命令 `uv run pytest tests/e2e/test_reflection_lifecycle.py::test_memory_mark_stale_proposal_can_be_approved_via_im_route -x -q`。
- [ ] 2.2 **实现（绿）**：改 `_reflection_helpers.approve_reflection_proposal_via_im`——`from tests.e2e._im_helpers import managed_agent_route_server`，用 `with managed_agent_route_server(stack) as base_url:` POST `{base_url}/im/route` 发 `approve`；移除 `gateway_port is None → pytest.skip` 降级。跑同一命令见绿（`proposal_status == "applied"`、`memory_status == "stale"`）。
- [ ] 2.3 清理：删除（或注明弃用）`_new_agent_gateway_port` 中仅服务于审批驱动的部分，避免误导后人。

## 3. skill 提案 approve（若已落地经 /im/route）

- [ ] 3.1 若 `test_reflection_scheduler_generates_pending_skill_proposal...` 或后续 skill approve 测试经 `/im/route` 审批，同样改用 spawned route server、去 skip；若 skill approve 仍为 deferred（design 判定），本组只在 tasks 注明 deferred，不强行。

## 4. 收尾 + lane

- [ ] 4.1 跑 `uv run pytest tests/e2e/test_reflection_lifecycle.py -q`：原 1 条 skip 转为 passed，其余仍绿（被 deferred 的 scenario 仍 skip/不存在而非 fail）。
- [ ] 4.2 `make test-e2e` 整套无新增失败/回归；确认本批仍**不在** `make test-pr`。
- [ ] 4.3 `make test-pr` 仍全绿（纯 test 侧、零 src，对照 main 基线无新增失败）。
- [ ] 4.4 边界自检：仅改 `tests/e2e/_reflection_helpers.py` + `tests/e2e/test_reflection_lifecycle.py`（必要时复用 `_im_helpers`）；**未改** `conftest.py::managed_stack` 核心、**未改** src。
