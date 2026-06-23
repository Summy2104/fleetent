## Context

地基 harness（`e2e-managed-stack-coverage`）已落地：`tests/e2e/conftest.py::managed_stack` 起真实多进程栈（platform + node + placed agent），`tests/e2e/_llm_stub.py` 提供确定性 LLM（回复 `stub: <last user text>`）。`ManagedStack` 暴露 `platform_url / node_id / agent_id / agent_name / admin_session_headers / home_dir / db_path / desired_state_cache_path`。`FLEETENT_NODE_INTERVAL_SECONDS=1`（drain 间隔已是小值，无需再调）。

本 change 在其上加三条用户可见链路的 e2e，注入策略=**在已有 HTTP/DB 边界注入观测**，不造假 transport、不改 src、不改 conftest 核心。

已核实的真实路径：
- IM 入站：agent `POST /im/route`（`runtime/agent_app.py:725`），body `ImRouteRequest`，头 `X-Fleetent-Principal`（node 注入），出 `ImRouteResponse.replies`。
- 审批 DM：高危工具 → `permission_gate.request_approval` → `_notify_approvers` 入队 `im_outbound_queue`；`approve <id>` 经 `/im/route` → `normalizer._match_approval_command`（`im_gateway/normalizer.py:475` 旁路）→ `approval_router.resolve_approval_request` → 恢复 run。
- fan-out：`outbound_connectors.notify_user`（`outbound_connectors.py:71`）入队 directed 行；node `_deliver_user_id_intent`（`node/im_edge.py:275`）经 `PlatformAddressResolver.resolve`（`im_edge.py:75`）→ `POST /nodes/{id}/identity/addresses`（`node_desired_state_api.py:149`）→ 逐绑定 `outbound.send_to`。
- 表 `im_outbound_queue`（`agent_state_migrations.py:503`）落 agent 侧 `agent_state.db`：id/platform/address_json/payload_json/dedup_key/status(pending|sent|failed)/attempts/created_at/sent_at。

## Goals / Non-Goals

**Goals**：端到端证明 ① IM 入站 → 同步回复 ② 高危工具 → 审批 DM 入队 → `approve <id>` → run 恢复 ③ `notify_user` fan-out 投递原语（注队列行 → node 反查 addresses → 入队形状/反查可观测）；helper 以新增方式提供，零 src 改动。

**Non-Goals**：
- **不测 reflection 全程**：reflection 提案 → 审批 → apply 的 directed-reach（A4b）整条链路归 D5（`e2e-reflection-lifecycle`）。本 change 只测 fan-out 的**投递原语**（直接注队列行，不经 reflection）。
- **不测真渠道投递**：无真 Slack/Telegram connector，投递腿发不出；真投递留给 integration（`test_node_im_outbound_queue` 已覆盖）。
- 不测网络后端（Postgres/Qdrant）；不重构核心 `managed_stack`。

## ⚠️ 关键可行性风险（apply 第 1 组 task 必须先用探针消解，不得假设）

1. **fan-out 投递腿无真 connector 发不出** → e2e 只能断言「入队形状正确 + node 尝试反查 `/identity/addresses`（平台侧可观测）+ 队列行状态从 pending 推进」。真投递留 integration。探针须确认：无 connector 下 node drain 的实际行为（`_deliver_user_id_intent` 在 `send_to` 失败时把行标 failed 还是 sent）与可观测点（平台 access log / 队列行 status / node 日志）。
2. **`/im/route` 怎么到达 agent**：现有 harness 的 chat ingress 走 `platform_url/admin/agents/{name}/chat`（经 forwarder），**agent 进程的直达 URL 不在 `ManagedStack` 字段里**。探针须确认：`/im/route` 是经 platform forwarder 转发，还是要拿 agent 进程端口直达；`X-Fleetent-Principal` 头怎么构造（node 注入格式，`decode_ingress_principal` 能解的形状）；是否需要 platform 的 `/nodes/{id}/identity/resolve` 在场。
3. **跨进程读 `im_outbound_queue`**：agent_state.db 真实物理路径定位（探针——可能落 `<home>/agents/<name>/...` 或经 tenant_router 落 `<data_dir>/<tenant>/<agent_id>/`）；drain 间隔已是 1s，用 `wait_for_condition`（conftest 已导出）轮询防 flaky，**不**用 sleep。
4. **fan-out 需 `im_users` 有绑定**：`PlatformAddressResolver` 反查命中前提是平台侧已为该 user_id 建好 IM 绑定。探针须确认怎么在平台侧建绑定（`im_gateway_management.resolve_or_provision` / `resolve_user_addresses` 的入口，可能经 `/nodes/{id}/identity/resolve` 或 admin API）。

## Decisions

- **边界注入，不造假 transport**：写入与触发走真实路径（`/im/route` 真发、审批真触发、directed 行真注 `im_outbound_queue`）；观测走平台侧 HTTP 可观测点 + agent 侧 DB 只读，不 mock 进程内对象。
- **新 helper 独占文件 `tests/e2e/_im_helpers.py`，不改 `managed_stack`**：放构造 Principal 头、注 directed 队列行、读 `im_outbound_queue`、建 IM 绑定等小工具；core `conftest.py` 冻结 → 与并行波 D2/D3/D5 零 `conftest.py` 合并冲突。
- **fan-out 只测投递原语，A4b 归 D5**：reflection → 审批 → apply 触发的 directed-reach 整链交 D5；本 change 的 fan-out 测试直接注队列行，刻意绕开 reflection，避免两 change 抢同一链路地盘。
- **审批 run 恢复的断言点由探针定**：优先用回复/可观测状态断言「run 恢复继续」；若 managed 下挂起 run 的恢复难直接观测，退而断言审批被解析为 approved + 队列/审批侧状态变化（探针确认最稳的可观测点）。

## Risks / Trade-offs

- 三处落盘点/达点不确定（风险 1–4）→ 用第 1 组探针先验消解，断言点据探针结论定，不写死假设。
- 起栈 + 多腿往返增加 e2e 时长 → 在 slow lane，可接受。
- fan-out 投递腿不可断言真送达 → 明确缩到「入队形状 + 反查发生」原语级，真投递归 integration（已有覆盖），避免假绿。
