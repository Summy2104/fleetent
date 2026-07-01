## 1. 硬化：单一 managed 信号 + fail-fast

- [x] 1.1 写测试：`runtime_placement.is_managed()` 仅依据 `FLEETENT_NODE_LOOPBACK_URL` 是否存在判定；三件套（NODE_ID/PLATFORM_URL/SERVICE_KEY）存在但无 loopback → 非 managed
- [x] 1.2 实现：新增 `runtime_placement.is_managed()`；`outbound_connectors.is_node_managed_runtime()` 收敛到它、废弃三件套判定
- [ ] 1.3 写测试：`resolve_for_runtime` 在"is_managed 为真但拿不到目标平台连接器"时不返回静默 `{}`，而是记 error 并使调用方得到明确失败信号
- [ ] 1.4 实现：`resolve_for_runtime` fail-fast（error 日志含 platform/agent/信号）；`send_file` 无连接器分支文案带诊断（platform、是否 managed）

## 2. node loopback 身份/地址端点

- [x] 2.1 写测试：`node/forwarder.py` 的 `POST /agent/{name}/identity/resolve` 与 `/identity/addresses` 用 agent TUI token 鉴权、node 补 service key 转发 platform `/nodes/{id}/identity/*`，返回体透传
- [x] 2.2 实现：两个 forwarder 端点（复用 `_forward_oauth` 转发范式 + `_check_agent_token`）

## 3. agent 侧身份/地址 resolver 注入

- [x] 3.1 写测试：`AgentIdentityResolver(owner, platform, platform_user_id)` 经 loopback（TUI token）返回 `user_id`；`AgentAddressResolver(user_id)` 返回地址列表
- [x] 3.2 实现：`im_gateway/access.py` 新增 `AgentIdentityResolver`/`AgentAddressResolver` + `set_im_address_resolver` seam（与既有 `set_im_identity_resolver` 并列）
- [x] 3.3 写测试：`agent_app.boot` 在 managed（有 loopback）注入两个 resolver；standalone（无 loopback）不注入 → 身份解析 passthrough
- [x] 3.4 实现：boot managed 分支接线两个 resolver（紧邻既有 managed-oauth 接线）

## 4. agent 自持 supervisor（managed）

- [x] 4.1 写测试：managed 启动路径不再强制 `--no-im`；agent boot 在有 IM token 时启动自己的 supervisor，并把活连接器注入 `NormalizedMessage.outbound_connectors`；无 token 则跳过不报错
- [x] 4.2 实现：`node/backend.py` spawn（LocalProcess + Container）去掉 `--no-im`；确认 boot `start_im` 在 managed 下生效、supervisor 从 agent `.env` 读 token

## 5. node 退出 IM 数据面

- [ ] 5.1 写测试：node reconcile **不**启动 Slack/Telegram supervisor、**不**调 `reload_bindings`；node 不打开任何 IM 接收连接
- [ ] 5.2 实现：`node/im_edge.py` 移除 supervisor 持有与 `reload_bindings`；移除出站 drain 循环；保留 identity/address loopback 代理接线
- [ ] 5.3 写测试：`/im/route` 入站端点已移除（managed 入站不再经 node 转发）
- [ ] 5.4 实现：移除 `runtime/agent_app.py` 的 `/im/route` 端点及其 `ImRouteRequest` 相关装配

## 6. 出站直发 + directed-reach 迁移

- [ ] 6.1 写测试：`resolve_for_runtime` 在 supervisor 已注入活连接器（非空）时直接返回之；回复/`send_file` 经活连接器直发、不入任何队列
- [ ] 6.2 实现：出站路径统一走活连接器；移除 `ManagedOutboundConnector`
- [ ] 6.3 写测试：`notify_user`（managed）经 loopback 反查 `user_id→地址` 并用活连接器 fan-out；单渠道失败只记日志、无绑定不投递只记日志；非 managed 仍 no-op
- [ ] 6.4 实现：`notify_user` 改为 agent 侧反查（`AgentAddressResolver`）+ 活连接器 fan-out；移除 `im_outbound_queue`（`outbound_queue_store`）与 node drain 的最后引用
- [ ] 6.5 实现：升级脚本 `scripts/upgrade.py` drop `im_outbound_queue` 表（全量切、无生产存量）

## 7. 审批投递经活连接器

- [ ] 7.1 写测试：managed 下审批提示经活连接器投递、approve/reject 回复由同一 agent 连接接收并关联回审批（不经 node drain / `/im/route`）
- [ ] 7.2 实现：审批提示投递与按钮/命令回收在 agent 自持连接上闭环（`permission_gate` 经 `outbound.send_to` 走活连接器；block_actions handler 随 supervisor 在 agent 进程）

## 8. 契约测试与收口

- [ ] 8.1 写契约测试：`managed == standalone` —— 相同输入下入站处理、文本回复、`send_file` 交付、审批 approve/reject 往返、directed-reach fan-out 的可观测结果一致
- [ ] 8.2 运行护栏 `uv run python scripts/check_module_boundaries.py` 与 `tests/unit/test_module_dependency_guardrails.py`，确认 agent 侧仍零 `import fleetent.platform.*`（loopback 仅 HTTP）
- [ ] 8.3 运行 `make test-pr` + `uv run pytest tests/integration -q`，对照 main 基线确认无新增失败
- [ ] 8.4 运行 `uv run mypy src` 与 `uv run ruff check src tests` 确认类型与 lint 通过
