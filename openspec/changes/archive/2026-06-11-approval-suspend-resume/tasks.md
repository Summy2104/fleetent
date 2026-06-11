## 1. StopReason + session meta 基础件

- [x] 1.1 Write failing tests: `StopReason.awaiting_approval` 存在；session manager 读写 `meta.pending_approvals`（增/查/删一条 pending）
- [x] 1.2 Implement `StopReason.awaiting_approval` + session meta pending_approvals 读写助手

## 2. gate 非阻塞登记

- [x] 2.1 Write failing tests: `request_approval` 登记审批 + 发提示后立即返回 `pending`，不 await；保留发提示（含 blocks）与授权集合记录（随 pending 可持久化的 approver 身份）
- [x] 2.2 Implement non-blocking `request_approval`（移除 event.wait；保留登记/通知/授权身份）

## 3. loop 挂起（placeholder + stop_reason）

- [x] 3.1 Write failing tests: `_plan_run_slots` 对待审批工具产出 placeholder 结果 `awaiting_human_approval (id=X)` 且不阻塞；run 检测到 pending → `StopReason.awaiting_approval` 结束 + 写 session meta；同批非门控工具照常执行
- [x] 3.2 Implement plan-phase suspend + run 主循环 awaiting_approval 收尾（正常保存 session，不触发 grace/budget）

## 4. 恢复（resume）核心

- [x] 4.1 Write failing tests: `resume_pending_approval(session_id, approval_id, decision)` —— approve 经 dispatch 执行工具 + 注入结果 context + 续跑到 final reply + 清 pending；reject 注入 declined + 续跑；恢复持 session 锁
- [x] 4.2 Implement resume entry（加载 session → 执行/拒绝 → 注入 → loop.run 续跑 → 清 pending）

## 5. 重启存活 + resolve 解耦 Event

- [x] 5.1 Write failing tests: `gate.resolve` 不依赖内存 Event（写 approvals 状态 + 授权校验）；模拟"无内存 Event"（fresh gate）下用持久化 pending + approvals 仍能 resolve；非授权身份重启后仍被拒
- [x] 5.2 Implement resolve 状态驱动 + 授权身份随 pending 持久化与重建

## 6. 待办式并发 + 过期清扫

- [x] 6.1 Write failing tests: pending 期间同 session 新普通消息走正常 turn（不被 steering 吞）；run 注入"未决审批"context；`cleanup_stale_approvals` 把超时 pending 标 timeout + 移除 meta 条目
- [x] 6.2 Implement pending-aware turn（注入 outstanding context）+ cleanup 回填

## 7. IM 恢复触发接线

- [x] 7.1 Write failing tests: normalizer `approve/reject <id>` resolve 成功后调 `resume_pending_approval`；slack `handle_approval_action` 按钮 resolve 后同样触发恢复；恢复输出经各自 reply_func/client 送出
- [x] 7.2 Implement normalizer + slack handler 恢复接线

## 8. 收尾

- [x] 8.1 改写受影响的既有阻塞式审批测试（permission_gate / loop / 集成）为挂起-恢复语义
- [x] 8.2 受影响层收尾：`make test-pr` 全绿；`uv run pytest tests/integration -q` 对照基线无新增失败
- [x] 8.3 本地 my-bot 实机 smoke：发起 send_im_message → 审批挂起（run 结束、可继续发别的消息不被吞）→ approve（按钮/文本）→ 工具执行送达；再测 reject、重启后 approve（手动，不进测试）
