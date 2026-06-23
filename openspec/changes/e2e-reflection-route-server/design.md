## Context

`e2e-reflection-lifecycle` 已落地 main 并归档。实跑 `make test-e2e` 时，`test_memory_mark_stale_proposal_can_be_approved_via_im_route` 在 `_reflection_helpers.approve_reflection_proposal_via_im` 处 `pytest.skip("managed agent /im/route gateway is not externally discoverable in this harness")`——因为它用 `_new_agent_gateway_port()` 扫描监听端口、按 `/health` 的 `agent` 字段匹配来"猜" node 拉起 agent 的 gateway 端口，猜不到就跳。结果 reflection 的 approve→apply 半程从未真验。

Wave B 的 `_im_helpers.managed_agent_route_server(stack)` 用另一条稳健路子：`reserve_port()` 取已知端口 → 起 `python -m fleetent agent run <name> --no-im --port <port> --home <agent_home>` 子进程（指向同一 agent home/DB）→ `wait_for_condition` 等 `/health` 就绪 → yield `http://127.0.0.1:<port>`。B 的 4 个 `/im/route` 测试全绿，证明此路可达可靠。

关键：`managed_agent_route_server` 只读 `stack.home_dir`、`.agent_name`、`.node_id`、`.platform_url`；`ReflectionManagedStack` 这四个字段都有 → **鸭子兼容，可直接复用**。

## Goals / Non-Goals

**Goals**：让 memory 提案 approve→apply e2e 真正执行（去掉 skip），用 B 已验证的 spawned route server 取代脆弱的端口扫描；reflection-lifecycle 名副其实地覆盖到 apply。

**Non-Goals**：不改 reflection src 行为；不动 `conftest.py::managed_stack` 核心；不改 B 的 `_im_helpers`（仅复用其 helper）；不扩展 reflection 覆盖范围（只补已 skip 的那条 + 顺带 skill approve 若适用）。

## Decisions

- **D1 直接复用，不搬家**：`_reflection_helpers` 直接 `from tests.e2e._im_helpers import managed_agent_route_server`，在 `approve_reflection_proposal_via_im` 内 `with managed_agent_route_server(stack) as base_url:` 然后 POST `{base_url}/im/route`。最小改动、最低风险。（备选：把该 helper 上提到共享 `_agent_route.py` 并让 `_im_helpers` re-export——更干净但触面更大，留作后续可选重构，本 change 不做。）
- **D2 删除 skip 分支**：移除 `gateway_port is None → pytest.skip` 的降级；`_new_agent_gateway_port` 不再用于审批驱动（可删或保留备用，倾向删以免误导）。
- **D3 TDD 红先行**：先让被 skip 的测试改为真断言 → 跑应见"红"（当前实现 skip ≠ 通过目标行为，符合"直接绿要先修测试"的纪律）→ 改 helper 用 route server → 见绿。

## ⚠️ 可行性探针（apply 第一步必验）

DB-seeded 的 reflection 提案，能否在**另起的 route-server 进程**里被 `approve <id>` 真正 resolve + apply？——memory 提案审批走 `approval_request_store`（DB 驱动）+ `reflection_gate.resolve_reflection_proposal_action`，非内存态 PermissionGate pending，故跨进程（route server 进程读 DB→apply→写回）理论可行；但 node 拉起的 agent 进程同时也持有同一 `agent_state.db`，须探针实测：① route server 进程处理 approve 后 `reflection_proposals.status` 真转 applied；② 两进程并发访问 `agent_state.db` 无锁问题（B 的审批测试已同样并发、绿，作旁证）。若探针发现 DB-seeded 提案需由原进程 resolve 才生效，design 据实调整（如改由 route server 进程内先触发/seed 再 approve）。

## Risks / Trade-offs

- 跨 helper 复用引入 `_reflection_helpers → _im_helpers` 依赖——可接受（皆 e2e 测试 helper）。
- 起额外 route-server 子进程略增单测耗时——e2e 在 slow lane，可接受。
