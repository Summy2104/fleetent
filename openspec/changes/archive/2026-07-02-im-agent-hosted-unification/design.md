## Context

现有 IM 有两条路径。**standalone**：`agent_app.boot`（`runtime/agent_app.py:720`，`start_im`）在 agent 进程启动 `SlackSupervisor`/`TelegramSupervisor`（`im_gateway/*_supervisor.py`，token 读自 `os.environ[bot_token_env]`），入站经 `normalizer.route` → `loop.run`，出站把活连接器塞进 `NormalizedMessage.outbound_connectors`（`im_gateway/slack.py:325/417`）直发。**managed**：node（`node/im_edge.py`）持 supervisor，入站经 `POST /im/route`（`agent_app.py`）转给 agent；出站 agent 入 `im_outbound_queue`（`ManagedOutboundConnector`），node `_drain_outbound_once` 投递。

managed 侧的脆弱点（均已核实）：
- **两套 managed 信号不一致**：OAuth 用 `FLEETENT_NODE_LOOPBACK_URL`（reconcile 写进 agent `.env`，`node/reconcile.py:_write_home`），而 `outbound_connectors.is_node_managed_runtime()`（:79）用 `FLEETENT_NODE_ID/PLATFORM_URL/SERVICE_KEY`——**这三者从未写入 agent `.env`**，容器后端 `--env-file .env`（`node/backend.py:130`）不继承 node 环境 → 恒缺 → `resolve_for_runtime` 返回 `{}`（:120）→ `send_file` 无连接器（`builtin_tools.py:1379`）。**这就是 AAA-8208 根因。**
- **静默失败**：`resolve_for_runtime` 空回退无日志。
- **分叉双维护**：managed-only 分支（队列/drain/ManagedOutboundConnector）被测程度低，是 bug 温床。

关键使能事实（已核实）：supervisor 纯 agent 侧、无 platform import、可复用（`slack_supervisor.py`）；IM token 已由 `referenced_env_names`=`collect_env_var_names`（含所有 `*_env`）写入 agent `.env`；身份/地址反查是 HTTP 契约（`node/im_edge.py:62-119` → platform `/nodes/{id}/identity/resolve|addresses`），可注入；node 已有 loopback 转发范式（`node/forwarder.py:212-258` 的 `_forward_oauth`，agent 用 TUI token）；发送走 Slack Web API（`chat.postMessage`），与 Socket Mode 接收解耦。

## Goals / Non-Goals

**Goals**
- 消灭 standalone/managed 分叉，统一为 agent 自持连接的单一路径。
- node 退出 IM 数据面（仅留 loopback 身份代理 + 进程监督）。
- 单一 managed 信号、fail-fast、`managed==standalone` 契约锁定。
- 全量切、一次到终态、不留 shim；agent 仍零 `import fleetent.platform.*`。

**Non-Goals**
- 不改 platform 侧 `im_users` 与 `/identity/*` 端点实现。
- 不引入灰度开关（`im_host`）——未上生产，全量切。
- 不改 MCP / 沙箱 / 审批策略语义（仅改审批消息的**投递载体**为活连接器）。

## Decisions

### D1：node 彻底不持 IM 接收连接（规避独占约束）
Slack Socket Mode 每 `app_token` 独占一条连接、Telegram 每 `bot_token` 单轮询光标。若 node 与 agent 同持接收连接会错乱。故 node **完全移除** supervisor 启动与 `reload_bindings`（`node/im_edge.py`），`backend.spawn` 去掉 `--no-im`（`node/backend.py:43,143`）。全量切、无双持窗口，因此**不需要原子切换/灰度**。
*备选*：per-agent `im_host` 灰度——否决（未上生产，徒增机制）。

### D2：出站发送走活连接器（Web API），directed-reach 同批迁移
agent supervisor 把活连接器注入 `NormalizedMessage.outbound_connectors`（同 standalone）。`resolve_for_runtime` 见非空即用，回复/`send_file`/审批直发。`notify_user` 不再入队，改为 agent 经 loopback 反查地址 + 用活连接器 fan-out。因此 `im_outbound_queue`/drain/`ManagedOutboundConnector` 一并移除（发送是 Web API，不依赖 Socket）。
*备选*：保留 node 出站 drain 做 directed-reach（Phase 桥）——否决（全量切，无需桥；留着即保留分叉）。

### D3：身份/地址 resolver 经 node loopback 注入 agent（agent 不持 service_key）
新增 `node/forwarder.py` 端点 `POST /agent/{name}/identity/resolve|addresses`，复用 `_forward_oauth`（node 补 service_key 转 platform）。agent 侧 `im_gateway/access.py` 新增 `AgentIdentityResolver`/`AgentAddressResolver`（读 `FLEETENT_NODE_LOOPBACK_URL` + `FLEETENT_TUI_TOKEN`），`agent_app.boot` managed 分支经 `set_im_identity_resolver`/`set_im_address_resolver` 注入。standalone 不注入 → passthrough（用平台原生 id）不变。
*备选*：agent 直调 platform（持 service_key）——否决（扩大凭证面；loopback 范式已有）。

### D4：单一 managed 判定信号
新增 `runtime_placement.is_managed()`，只读**已确证投递**的 `FLEETENT_NODE_LOOPBACK_URL`。`outbound_connectors.is_node_managed_runtime()` 收敛到它，废弃三件套判定。这直接消除 AAA-8208 的信号错配。

### D5：fail-fast，杜绝静默交付丢失
`resolve_for_runtime`（及 `send_file` 无连接器分支）在"managed 但拿不到连接器"时记 **error 日志**（含 platform/agent/信号状态）并返回明确错误文案，不再静默 `{}`。

### D6：契约测试锁定 `managed == standalone`
新增契约测试：同一输入下 managed（agent 自持）与 standalone 的收发、`send_file` 交付、审批 approve/reject 往返、directed-reach fan-out 行为等价，防分叉复活。

## Risks / Trade-offs

- **连接生命周期随 agent 进程（重启即重连）** → 缓解：Slack Socket Mode 秒级重连 + 事件重投；加重连退避。用户已接受此权衡（原因#3）。
- **token 进入 agent 进程** → 缓解：env-only（不入 agent.yaml）、`build_sandbox_env` 默认 `include_host=False`（`integrations/sandbox/secrets.py:47`）不透传沙箱；信任级别同 standalone（standalone 本就如此）。
- **身份解析每消息一次 loopback 调用** → 缓解：node 常在；加 `platform_user_id→user_id` 结果缓存（TTL）。
- **移除队列/drain 的回归面** → 缓解：D6 契约测试 + 移除前跑全量 integration 对照 main 基线；`im_outbound_queue` 表由升级脚本 drop（无生产存量）。
- **护栏**：agent→node 仅 HTTP，不 import platform；`test_module_dependency_guardrails` 须保持绿。

## Migration Plan

全量切、不留 shim。落地顺序（单个 change 内 TDD 分组）：先硬化（D4/D5 单信号 + fail-fast）→ 接线 agent 自持（supervisor + resolver 注入 + 出站直发）→ 移除 node IM 数据面（supervisor/`/im/route`/drain/队列/`ManagedOutboundConnector`）→ directed-reach 迁移 → 契约测试收口。升级脚本 drop `im_outbound_queue`。回滚：本 change 未合入 main 前于功能分支验证；合入前经契约 + integration 基线确认。

## Open Questions

- 身份缓存 TTL 默认值（倾向 60s）。
- node loopback 身份端点是否复用 `DEFAULT_FORWARDER_PORT`（倾向复用，与 OAuth 同端口同鉴权）。
