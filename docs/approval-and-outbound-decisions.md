
## 审批挂起-恢复（approval-suspend-resume，已实现）

把审批从「阻塞 run 的 asyncio.wait（最长 1h 悬挂协程）」重构为「挂起-恢复 / placeholder 待办式」。

### 决策

- **D1 placeholder 闭合协议**：待审批工具的 tool_call 紧跟一条合成结果 `awaiting_human_approval (id=X)`，history 始终合法（无 dangling tool_call）；批准后真实结果作为下一回合 context 注入。否决 deferred-commit（交错新消息时序重建乱）。
- **D2 pending 存 session 文件 meta**（`meta.pending_approvals`，agent 侧，不写 platform 表）；approvals 表仍记审批生命周期，按 approval_id 关联。
- **D3 新 `StopReason.awaiting_approval`**（非终态，区别于 approval_rejected 终态）；run 以此结束时正常保存、不触发 grace/budget。
- **D4 恢复 = 执行工具 → 注入结果 → 续跑 run**（`runtime/approval_resume.resume_pending_approval`，`continue_run` thunk 由 IM 边缘提供，解耦 run 参数膨胀）。
- **D5 resolve 解耦内存 Event**：改 `_pending` 集合 + approvals 表状态驱动；授权身份随 pending 持久化（session meta `approver_ids`），重启后 IM 边缘传 `authorized_actors` 给 `resolve()`，仍只有授权人能批。
- **D6 待办式并发**：run 挂起后 `run()` 返回 → `steering.is_running` 自然为 False，steering 吞消息问题结构性消失；run 注入「未决审批」context 防模型重发同一 gated 工具（防重发是正确性必需，非用户提醒）。
- **D7 过期回填**：启动 `cleanup_stale_approvals`（blanket-timeout）**改为** `reconcile_expired_approvals`（只清真正过期的、保留未过期 pending → 重启存活）；默认窗口放宽到 24h（无悬挂协程）。

### Resolved（原 Open Questions）

- 恢复续跑用**独立**预算/turn 计数（新 run，不接续；挂起跨越真实时间）。
- **不做**用户可见 pending 复现提醒（YAGNI；审批卡片在会话内可见 + 过期回填兜底）。

### 范围 / Non-Goal

- 限 IM 路径（Slack 文本命令 + 按钮、Telegram 文本命令）；**TUI/HTTP 流式路径维持现状阻塞**（follow-up）。
- 连带修复：steering 吞消息（📝 已把你的补充发给正在进行的任务）、群聊同线程被锁、5 分钟锁死。

### 执行记录

- 8 task group 严格 TDD（红→绿）；改写了一批旧阻塞模型测试（permission_gate routing/allowlist、integration permission_gate / im_gateway / standalone-approval）为挂起-恢复语义。
- 预存失败 `test_deployment_docs::test_pilot_install_checklist...`（main 同样失败）非本 change 引入，未处理。
