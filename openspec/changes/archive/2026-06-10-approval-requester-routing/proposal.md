## Why

审批模型缺「请求用户本人确认」一档：现状所有 medium/high 审批一律外呼 `approval_routing` 配置的审批人，但 medium 级操作（agent 替用户发消息/邮件等用户自担后果的代理动作）的合适审批人是**发起用户本人**——只有他有上下文判断内容对不对。`permission-gate` 主 spec 的 Purpose 本就写明「medium 向请求者本人发确认、high 向预配置审批人发审批」，实现（R1）未兑现这一档。同时 `gate.resolve()` 不校验决策者身份（任何拿到 approval_id 的人都能批），requester 模式审批提示发在会话内（可能是频道），该洞必须先补上。

## What Changes

- **`requester` 哨兵路由**：`approval_routing` 的 `approvers` 列表接受 `requester` 哨兵值（与 `platform:target_id` 地址并存）。gate 解析到它时，审批提示经 `reply_func` 发回**当前会话**（请求用户原地回 `approve <id>` / `reject <id>`），不再外呼
- **决策身份校验（补洞）**：每个审批请求记录授权决策人集合（requester 路由 = 发起人 `requester_user_id`；外呼路由 = 实际通知到的审批人 target id）。`gate.resolve()` 拒绝集合外的身份（返回 False，pending 不变，记 warning 日志）
- **无会话回落**：`reply_func` 不可用（如定时任务上下文）时 `requester` 哨兵不可达，继续尝试列表内其余外呼地址；全部不可达 → 沿用 default-closed 立即拒绝
- **默认行为不变**：`requester` 须显式配置；未配置的部署行为与现状完全一致
- 分层约定写入 spec：medium = 用户自担后果层（推荐配 `requester`）、high = 系统影响层（写入面超出发起用户资源域，配平台审批人）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `permission-gate`: 新增 requester 路由与决策身份校验两条 requirement；Async approval wait 不变

## Impact

- **代码**：`agent_config.py`（`resolve_approvers` 解析 `requester` 哨兵）、`governance/permission_gate.py`（requester 路由经 reply_func、授权集合记录与 resolve 校验）
- **调用方兼容**：`normalizer.route()` 传 `msg.user_id`、TUI `dispatch` 传 `conn.user_id`——均与各自 run 的 `requester_user_id` 同源，requester 模式自洽；外呼模式授权集合存 target id（裸 id 比对，跨平台同名碰撞风险可忽略）
- **不改**：审批存储 schema、超时机制、approve/reject 文本命令格式、approval-minimization 指纹机制
