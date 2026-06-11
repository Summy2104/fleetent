## Why

medium/high 工具审批当前在 run 内部用 `asyncio.wait_for(event.wait())` **阻塞整个 run** 等待人工决定（medium 300s / high 3600s）。这条阻塞带来四个连锁问题：

1. **steering 吞消息**：等审批 ≠ 在干活，但 `steering.is_running(session_id)` 为 True，用户在同 session 发的普通消息被当作"补充"并进正等审批的任务（实测 `📝 已把你的补充发给正在进行的任务`），群聊同线程他人也被一起锁住
2. **悬挂协程**：high 风险一个协程带完整上下文挂最长 1 小时，纯占用
3. **重启即丢**：审批挂在内存 `asyncio.Event`，进程重启等待中的 run 直接蒸发，用户请求凭空消失（`approvals` 表已持久化、本意就是跨重启存活，但 run 侧没跟上）
4. **被迫的短超时**：正因不能永远挂协程，才不得不设 300s/3600s 上限

根因是把"审批等待"建模成了"阻塞的协程"。本 change 改为 **挂起-恢复（placeholder 待办式）**：审批不阻塞 run，发起后 run 立即结束并持久化挂起状态；人工决定（按钮/文本命令，可在重启后）触发恢复，执行工具并续跑到最终回复。

## What Changes

- **gate 非阻塞登记**：`request_approval` 登记审批 + 发提示卡片后立即返回 `pending`，不再 `event.wait()`
- **loop 挂起**：`_plan_run_slots` 对待审批工具不再等待，写一条 placeholder 工具结果 `awaiting_human_approval (id=X)` 使 history 始终合法（无 dangling tool_call）；run 以新 `StopReason.awaiting_approval` 结束；pending 映射 `{approval_id → tool_call_id, name, args}` 写入 session 文件 `meta`（agent 侧，不进 platform 表）
- **恢复触发**：`approve/reject <id>`（Slack 按钮 handler / normalizer 文本命令）resolve 后，若该 approval 关联 session 的 pending：**批准** → 执行该工具、真实结果作为下一回合 context 注入并续跑 run；**拒绝** → 注入「用户拒绝」context 续跑
- **重启存活**：resolve 不再依赖内存 `Event`；pending 落 session 文件 + `approvals` 表，进程重启后仍可批准并恢复
- **过期清扫**：`cleanup_stale_approvals` 把超时审批回填占位结果使会话一致；审批窗口可放宽（不再受协程悬挂成本约束）
- **待办式语义**：pending 期间同 session 新消息**照常处理**（history 已合法），LLM 经注入知晓 X 挂起；不强制模态聚焦

## Capabilities

### New Capabilities

- `approval-suspend-resume`: 审批挂起-恢复机制——run 遇待审批工具写 placeholder 并以 awaiting_approval 结束、pending 状态持久化到 session、resolve 后执行/拒绝并续跑、重启存活、过期回填

### Modified Capabilities

- `permission-gate`: 「Async approval wait」从阻塞 `event.wait()` 改为非阻塞登记 + 挂起；「Approval timeout」从 auto-reject 阻塞协程改为清扫回填占位

## Impact

- **owning packages**：`governance`（permission_gate 非阻塞）、`runtime`（loop 挂起 + termination 新枚举）、`session`（manager meta pending_approvals）、`im_gateway`（normalizer / slack 恢复触发）
- **public API surface**：`StopReason.awaiting_approval`；`PermissionGate.request_approval` 返回语义（pending）；session meta `pending_approvals` 字段；恢复入口函数（如 `resume_pending_approval`）
- **owned tables**：无新表（复用 `approvals`；pending 映射在 session 文件 meta）
- **config namespace**：无新增（复用 `permission_gate_*` / `approval_routing`）
- **cross-module dependencies**：im_gateway → runtime（恢复调 loop）、runtime → session（写 meta）；不新增 agent→platform 反向依赖
- **migration / shim**：纯增量；阻塞式审批的既有测试需改写为挂起-恢复断言
- **范围**：限 IM 路径（Slack / Telegram）。**Non-Goal**：TUI/HTTP 流式路径维持现状阻塞（流式恢复另案 follow-up）
