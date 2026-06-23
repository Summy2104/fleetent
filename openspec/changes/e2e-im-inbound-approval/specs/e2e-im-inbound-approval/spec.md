## ADDED Requirements

### Requirement: IM 入站经 `/im/route` 同步回复 e2e

SHALL 有一条 e2e 验证：在真实多进程 managed 栈下，一条 IM 入站消息经 agent `POST /im/route`（携 node 注入的 `X-Fleetent-Principal`，body 为 `ImRouteRequest`）进入，经 `normalizer.route` → loop → 确定性 LLM stub，最终以 `ImRouteResponse.replies` 同步返回回复。

#### Scenario: 入站消息得到同步回复

- **WHEN** 向 managed 栈中 placed agent 的 `/im/route` 发送一条 `ImRouteRequest`（platform/session_id/user_id/text + 合法 Principal 头）
- **THEN** 响应 200 且 `replies` 非空，回复内容来自确定性 LLM stub（可断言其确定性标记）

### Requirement: 高危工具审批 DM 往返恢复 run e2e

SHALL 有一条 e2e 验证：高危工具触发 `permission_gate.request_approval` → `_notify_approvers` 向 agent 侧 `im_outbound_queue` 入队审批通知；随后用户经 `/im/route` 发送 `approve <id>` → `normalizer` 命中审批命令旁路 → `approval_router.resolve_approval_request` → 原挂起的 run 被恢复继续。

#### Scenario: 审批通知入队

- **WHEN** 一次 run 触发高危工具进入审批挂起
- **THEN** agent 侧 `im_outbound_queue` 出现一条 `status=pending` 的审批通知行（platform/address/payload 形状正确）

#### Scenario: `approve <id>` 恢复挂起的 run

- **WHEN** 用户经 `/im/route` 发送 `approve <approval_id>`
- **THEN** 该审批被解析为 approved，对应挂起的 run 恢复并继续执行（可经回复或后续可观测状态断言恢复发生）

### Requirement: `notify_user` fan-out 投递原语 e2e

SHALL 有一条 e2e 验证 directed-reach 的 fan-out 投递原语：直接向 agent 侧 `im_outbound_queue` 注一条 directed 目标行（`platform=directed`、`address_json={"target_type":"user_id","user_id":...}`），node drain 解析该 directed 意图后经 `PlatformAddressResolver` 调用 `POST /nodes/{node_id}/identity/addresses` 反查该 user_id 的全部绑定地址，并对每个绑定尝试 fan-out。本 e2e 只断言「入队形状正确 + node 发生地址反查（平台侧可观测）」，**不**断言真渠道投递成功（无真 Slack/Telegram connector）。

#### Scenario: directed 队列行被 node drain 拾取并反查地址

- **WHEN** 向 agent 侧 `im_outbound_queue` 注一条 directed user_id 目标行，且平台侧已为该 user_id 建好至少一条 IM 绑定
- **THEN** node drain 拾取该行并触发对 `/nodes/{node_id}/identity/addresses` 的反查（平台侧可观测到该反查发生），队列行状态从 `pending` 推进（`sent` 或 `failed`，因无真 connector）

#### Scenario: 注入形状即 directed-reach 投递契约

- **WHEN** 检视注入的 directed 队列行
- **THEN** 其 `platform`、`address_json`、`payload_json`、`dedup_key`、`status` 各列形状符合 `im_outbound_queue` 的 directed-reach 投递契约

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程 e2e SHALL 在独立 slow/nightly lane 运行（`make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁（`make test-pr`）
- **THEN** 不运行本 change 的 IM 入站 / 审批 / fan-out e2e（它们在独立 `make test-e2e` lane）
