## 1. 平台反向地址解析（TDD）

- [ ] 1.1 写测试（先红）：`im_gateway_management.resolve_user_addresses(user_id)` 查 `im_users WHERE user_id=X` 返回全部 `(platform, platform_user_id)`；无绑定返回空。先跑见红。
- [ ] 1.2 实现（绿）：在 `platform/im_gateway_management/identity.py` 加 `resolve_user_addresses(user_id)`。见绿。
- [ ] 1.3 写测试（先红）：`POST /nodes/{node_id}/identity/addresses`——node-key 认证、入 user_id、出 addresses；无 key/坏 key 拒。先跑见红。
- [ ] 1.4 实现（绿）：在 `node_desired_state_api.py` 加端点（镜像 `post_identity_resolve`，`_authenticate_node` 依赖）。见绿。

## 2. node 反向 client + drain fan-out（TDD）

- [ ] 2.1 写测试（先红）：`PlatformAddressResolver`（仿 `PlatformIdentityResolver`）调 `/identity/addresses` 返回地址列表。先跑见红。
- [ ] 2.2 实现（绿）：`node/im_edge.py` 加 `PlatformAddressResolver`。见绿。
- [ ] 2.3 写测试（先红）：drain 遇 `target_type="user_id"` 意图 → 反查 → 全发每个绑定渠道（fan-out）；无绑定→不投递+日志；单渠道失败→记日志+继续其余+不中断 drain。先跑见红。
- [ ] 2.4 实现（绿）：im_edge 出站 drain 加 `target_type` 分支（`"user"`=现状直发；`"user_id"`=反查+fan-out 舱壁化）。见绿。

## 3. agent 侧 notify_user intent（TDD）

- [ ] 3.1 写测试（先红）：node-managed 下 `notify_user(user_id, message)` 入队一条 `target_type="user_id"` 意图到 `im_outbound_queue`，不调 platform、不查 im_users。先跑见红。
- [ ] 3.2 写测试（先红）：非 managed（`is_node_managed_runtime()` False）下 `notify_user` no-op + 日志、不抛。先跑见红。
- [ ] 3.3 实现（绿）：`outbound_connectors` 加 user_id-目标入队路径；runtime 加 `notify_user(user_id, message, *, blocks=None)` 薄出口（managed 入队 / 非 managed no-op）。见绿。

## 4. A4b 接入 reflection（TDD）

- [ ] 4.1 写测试（先红）：reflection 的 user-memory 提案通知改调 `notify_user(proposal.user_id, <含 approve/reject id 的提示>)`；shared/skill 提案**不变**（仍走原配置地址路径）。先跑见红。
- [ ] 4.2 实现（绿）：在 reflection 提案通知点（`_notify_pending_proposal` 等）对 user-memory 分支改走 directed-reach；shared/skill 不动。见绿。
- [ ] 4.3 回归：确认 owner 回复关联回 memory_proposal 的既有审批链未受影响（既有审批 resolve 测试仍绿）。

## 5. spec 文档对齐（archive 时同步）

- [ ] 5.1 `opsx:archive` 新增 capability `directed-reach`（delta 已在 change specs/ 下，落到 openspec/specs/directed-reach/）。

## 6. 收尾门禁

- [ ] 6.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [ ] 6.2 `make test-unit-ci` 通过（CI 覆盖率关 coverage --fail-under=76）。
- [ ] 6.3 跑相关测试：reflection + outbound_connectors + node im_edge + im_gateway_management identity + node_desired_state_api 相关单测，及 `uv run pytest tests/integration -q`（端点/drain 跨进程，对照 main 基线无新增失败）。
- [ ] 6.4 `uv run python scripts/check_module_boundaries.py` 通过（确认 agent 侧未 import platform、notify_user 不调 platform，反查只在 node→platform）。
