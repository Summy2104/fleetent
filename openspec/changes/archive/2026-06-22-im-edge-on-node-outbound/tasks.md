## 1. im_outbound_queue 表（agent_state embedded-Y 迁移）

- [x] 1.1 **测试（红）**：agent_state.db 跑迁移到 head 后含 `im_outbound_queue`（id/platform/address_json/payload_json/dedup_key/status/attempts/created_at/sent_at）；enqueue + 读 pending + 标 sent 的 store helper。先跑见红。
- [x] 1.2 **实现（绿）**：`agent_state_migrations.py` 加 `im_outbound_queue`（embedded-Y，**非 alembic**）+ store helper（enqueue/list_pending/mark_sent/mark_failed）。跑见绿。

## 2. agent 出站 emitter 改 mode-aware

- [x] 2.1 **测试（红）**：出站 emitter——**managed**（无 live connector / 有平台-node 注入）→ **写 `im_outbound_queue`**；**standalone**（connector_registry 有 connector）→ 进程内直发（现行）。覆盖三源：permission_gate 审批 DM、cron fire 出站、send_im_message 工具，都经同一 emitter。先跑见红。
- [x] 2.2 **实现（绿）**：把 `agent_app.py:422` connectors_resolver/出站发射点抽象成 emitter（managed=enqueue / standalone=connector_registry.snapshot 直发）；确认 permission_gate(`outbound_connectors`)、cron(`_fire` connectors)、send_im_message 都经它。跑见绿。

## 3. node drain（im_edge.py）

- [x] 3.1 **测试（红）**：node drain 读本机 agent `im_outbound_queue` pending → 经该 agent connector 发出 → 标 sent；**at-least-once + dedup**（标记前重启 → 重取但凭 dedup_key 不重复发）；发送失败 → attempts+1 留 pending 待重试。先跑见红。
- [x] 3.2 **实现（绿）**：`node/im_edge.py` 加周期 drain（复用 node 轮询间隔），经 connector 发出 + dedup + 状态流转。跑见绿。

## 4. 收尾

- [x] 4.1 **standalone 保真回归**：standalone（无注入）下异步出站仍进程内直发、不写队列、`fleetent agent run` IM 不变。
- [x] 4.2 边界核验：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + 依赖护栏（im_gateway 仍不 import platform；node 读本机 agent 队列="读 agent 产物"；无 agent→platform）。
- [x] 4.3 **跨切面收尾**（跨 runtime/node/im_gateway/governance/cron）：`make test-pr` 全绿（对照 main 基线无新增失败）+ 跑**全量集成** `uv run pytest tests/integration -q`（重点 im/permission_gate/cron/node/forwarder 类，判"无新增失败"）+ 覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [x] 4.4 （建议）live 实证：以 automated managed queue/node drain integration + standalone targeted regression 替代手工 live 验证，确认 managed 审批 DM / send_im_message 经队列+node drain，standalone 仍进程内直发。
