## Why

人在回路的工具审批今天是**平台耦合、且只能单体运行**的机制：门的活状态是进程内 `asyncio.Event`；`approvals` 表由 agent 运行时经 `user_store._conn` **写进平台/管理库**（已知的 agent→platform 泄漏点 #1）；审批请求被回给**触发动作的人**，而非路由到指定审批人。这违反两条核心契约——agent 必须能脱离 platform 独立运行、platform 不参与 agent 运行时——且跨进程根本无法工作（platform 侧审批消费者至今是 placeholder 即为佐证）。

权威目标设计见 `docs/architecture/data-model.md` §5.5（R1 审批契约）。本变更把审批做成**完全由 agent 自持的能力**：agent 主动联系指定审批人、门状态落 agent 侧、不再触碰任何 platform 代码/表——使审批在单机与受管下行为一致，platform（若在场）至多是只读下游观察者。

## What Changes

- **新增** im_gateway 可向**指定用户/频道主动发送**消息（Slack `chat_postMessage` 开 DM、Telegram `send_message`）；今天做不到——只有被动回复。编码平台可达性规则（Telegram 不能私信没 /start 过的用户；Slack 可向任意工作区用户开 DM）。
- 审批改为 **请求者 ≠ 审批人**：撞到风险门时 agent 经新出站原语**主动私信配置的审批人**，而非回触发会话。审批回执按 `approval_id` 关联（normalizer 中已与线程无关）。
- **新增** `agent.yaml` 审批人路由配置（`approval` 块）：主轴 `by_risk`（medium/high）+ 按工具 `by_tool` 覆盖；审批人用内部 user_id 经 im-user-mapping 解析为 IM 地址；多人策略 any/all；兜底 `on_no_approver: reject`（未配置/DM 发送失败/超时一律拒，default-closed）。取代连接器级 `ConnectorAccess.require_approval`。
- **BREAKING（内部）** `permission_gate` 停止 `import fleetent.user_store`（`_conn`/`DB_PATH`）；门请求+状态经 **agent 自持 store 边界**持久化；`approvals` 访问路径与管理库解耦，其**双 schema 权威**（alembic 060 + `_init_db`）收敛为仅 agent 侧。
- 审批人仅存为**不透明 actor 标签**（非 platform `users` 外键），使 agent 不持有 platform 身份——为未来 Identity 端口铺路而不依赖它。
- Bug 修复：`approvals.session_id` 当前永远写 `""`；重启后进程内 event 丢失、所有 pending 被强制超时（"跨重启存活"是假的）。

> 不在本变更范围（后续 change）：物理拆库 / 五库拓扑（#3）；完整 Identity 端口（#4，本期用不透明字符串占位）；platform 只读审批投影（A3）。

## Capabilities

### New Capabilities
- `im-outbound-messaging`: agent 发起的、向指定用户/频道投递消息的能力，跨 Slack/Telegram，带各平台可达性规则。

### Modified Capabilities
- `permission-gate`: 推广为 **请求者≠审批人 + 经出站 DM 主动联系指定审批人**（现 spec 已述 high risk 发"预配置审批人"，但实现未真正外呼——本期补齐并推广到 medium）；门状态落 **agent 侧、与管理库解耦**；审批人存**不透明 actor 标签**；**停止 import user_store**；收敛 `approvals` 双 schema 权威；修 `session_id` 与重启耐久性 bug。
- `permission-gate-config`: 在 `AgentFile` 增加 `approval` 路由块（`by_risk` + `by_tool`、审批人、`any/all` 策略、`on_no_approver` default-closed），并厘清与既有 `permission_gate_enabled` 的关系、取代连接器级 `require_approval`。

## Impact

- **代码**：`im_gateway/{slack,telegram}.py`（出站发送）、`im_gateway/normalizer.py`（审批关联）、`governance/permission_gate.py`（重构、去 `user_store` 依赖）、`agent_config.py`（`AgentFile.approval`）、agent 侧审批 store（新 store 边界）、`runtime/loop.py`（门调用接线）、`runtime/agent_app.py`（resolve 端点不变）。
- **Specs**：新增 `im-outbound-messaging`；修改 `permission-gate`、`permission-gate-config`。
- **解耦**：就地消除 permission_gate 处的 agent→platform 泄漏（#1）；审批须通过"无 platform"单机护栏。
- **依赖**：无新增外部依赖；Slack/Telegram 出站复用现有 SDK（slack-bolt client、python-telegram-bot）。
- **测试**：im_gateway 出站（mock Slack/Telegram HTTP）、permission_gate 重构（agent 侧 store、不透明 actor）、路由 schema（AgentFile 解析）、单机审批仍可用。
