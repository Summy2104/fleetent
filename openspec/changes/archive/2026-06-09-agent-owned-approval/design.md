## Context

权威设计见 `docs/architecture/data-model.md` §5.5（R1 审批契约）。当前 `governance/permission_gate.py` 的现状（已摸查）：

- 活门是进程内 `asyncio.Event` + `_decisions` dict；`approvals` 表经 `from fleetent.user_store import _conn, DB_PATH` 写进**管理库**——agent 运行时写管理库即越界（#1 泄漏链）。
- delivery 方向已对：审批请求经 `reply_func` 顺响应流回、resolve 走 agent 自己的 API（`/approvals/{id}/resolve`、TUI `METHOD_APPROVE`、IM normalizer）——TUI/IM/HTTP 都是 agent 客户端。
- 但请求被回给**触发者**，没有"路由给指定审批人 + 主动外呼"；`approvals` 同时由 alembic 060 与 `_init_db` 定义（双权威）；`INSERT` 的 `session_id` 永远写 `""`；重启后内存 event 全丢、`cleanup_stale_approvals` 把 pending 全标 timeout（"跨重启存活"是假的）。
- im_gateway 无主动外呼能力（出站仅 telegram 打字指示器；Slack 回复用 bolt `say()` 绑触发线程）。

约束：agent 必须能脱离 platform 单机运行；agent 运行时不得 `import fleetent.platform.*`；遵循 TDD hard gate、store 边界、named params。

## Goals / Non-Goals

**Goals：**
- im_gateway 新增"向指定目标主动发送"原语（Slack DM / Telegram send_message）+ 可达性校验。
- 审批改为请求者≠审批人：撞门→查路由→主动 DM 审批人→按 `approval_id` 关联回执。
- 审批人路由配置（`AgentFile.approval`：`by_risk`+`by_tool`、`any/all`、`on_no_approver: reject`）。
- permission_gate 去 `user_store` 依赖；门状态落 agent 侧 store；`approvals` 单一 schema 权威（agent 侧）；actor 存不透明标签；修 `session_id` 与重启 bug。

**Non-Goals（后续 change）：**
- 物理拆库 / 五库拓扑（#3）；完整 Identity 端口（#4，本期 actor 用不透明字符串占位）；platform 只读审批投影（A3）。
- 跨进程 resolve（platform 独立进程放行）——本期只保证单机 agent 进程内自洽，跨进程留给拓扑/投影期。

## Decisions

**D1：出站原语作为 im_gateway 的新能力，按连接器适配。** Slack 用 `client.chat_postMessage`（先开 DM 频道）、Telegram 用 `bot.send_message(chat_id)`。暴露 `is_reachable(target)` 编码平台约束。备选：复用 `reply_func`——否决，它绑触发线程、无法外呼第三人。

**D2：approver 路由解析 = 配置 → user_id → IM 地址。** `approval` 块给 user_id，经既有 im-user-mapping（`(platform, platform_user_id) ↔ 内部 user`）反查可触达地址。备选：直接在配置里写 IM 地址——否决，泄漏部署细节、不可移植。

**D3：门状态落 agent 侧 store，不碰管理库。** 新增一个 agent 自持的审批 store（`ensure_schema` 自建、named params、不 `import user_store`）。本期物理上仍可落当前 agent DB 文件（#3 之前），关键是**访问路径**与 schema 权威归 agent 侧——这就地断 #1 在 permission_gate 处的泄漏。`approvals` 从 alembic 移除由 #3/#2 协调；本期 agent 侧 store 自建该表、并加守卫断言它不再走 `user_store._conn`。

**D4：actor 不透明。** resolve 传入的 approver 标识原样存字符串，不 join `users`。为 #4 Identity 端口铺路而不依赖它。

**D5：default-closed 一以贯之。** 未解析出审批人 / DM 发送失败 / 超时——全部 reject。与既有 `ConnectorAccess.require_approval` 默认关一致。

**D6：medium 与 high 对称，无"自我确认"回落。** 推广"请求者≠审批人"到 medium 与 high；二者都从 `approval` 解析审批人，解析不到即按 `on_no_approver`（default-closed）拒绝。**不提供"请求者本人确认"回落**——自我确认对风险门毫无意义（请求者给自己的危险动作点"是"等于无门）。若要让某工具不设门，应降其 `risk_level=none` 或设 `permission_gate_enabled=false`，而非靠自我确认。

## Risks / Trade-offs

- **[Telegram 不能私信未 /start 用户]** → `is_reachable` 显式判假，触发 default-closed reject + 清晰告知，而非静默挂起。
- **[`approvals` 仍物理在当前 DB 文件（#3 前）]** → 本期只保证 schema 权威 + 访问路径归 agent 侧并加护栏；物理搬迁留 #3，不在本期制造半拆状态。
- **[移除 alembic 对 approvals 的定义可能与管理库冲突]** → 本期不删 alembic 迁移历史；改为 agent 侧 store 自建 + 测试断言 permission_gate 不再经 `user_store` 访问；alembic 侧的退场由 #2/#3 处理。降低单期爆炸半径。
- **[medium 语义变化]** → 通过 D6 回落保持兼容；既有"medium→请求者确认"场景仍绿。
- **[重启耐久性]** → 本期修 `session_id` 与"盲目全标 timeout"；不承诺跨进程/跨重启恢复被阻塞的 run（诚实留作已知限制，归拓扑期）。

## Migration Plan

1. 先落 A1 出站原语（独立、可单测），不改审批逻辑——可单独验证。
2. 再落 A2：`AgentFile.approval` 解析 → 路由解析 → permission_gate 重构（消费 A1 外呼、agent 侧 store、去 user_store、不透明 actor）。
3. 行为变更告知：既有"medium→请求者自我确认"被**显式移除**（自我确认无意义）。迁移说明须提示运营方：原依赖该行为的 agent 必须改配审批人，或把对应工具降为 `risk_level=none` / 设 `permission_gate_enabled=false`，否则这些 medium 工具将按 default-closed 被拒。
4. 回滚：A 是新增能力 + 内部重构；回滚即不启用 `approval` 块并恢复旧 permission_gate 模块。

## Deferred（已登记，不得遗漏）

- **`approvals` 表的 Alembic 定义（迁移 060）本期不删**，仅让 agent 侧 store 成为唯一写入/建表权威并去 `user_store` 耦合 + 加护栏。但该 Alembic 定义**必须在 #2（管理表收编）或 #3（物理拆库）中退场**：届时确认 agent 侧 store 已是唯一权威后，删除/废弃 alembic 对 `approvals` 的建表，消除双 schema 权威。已同步登记到持久层 roadmap #2 范围与 `docs/architecture/data-model.md` §5.2（过渡件）。

## Open Questions

- A3 platform 只读审批投影的读取契约（读 agent 侧审批 store 还是 trace）留到 A3 期定。
