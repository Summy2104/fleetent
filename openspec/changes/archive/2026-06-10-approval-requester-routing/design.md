## Context

现状（已核实）：

- `agent_config.resolve_approvers()` 只接受 `platform:target_id` 格式，无冒号条目静默跳过——`requester` 哨兵会被丢弃
- `permission_gate.request_approval()` 经 `_notify_approvers()` 外呼所有审批人；`reply_func` 在手但只用于"已拒绝/等待中"通知
- `gate.resolve()` 不校验决策者：approver_user_id 仅作 opaque actor 存档（D4），任何拿到 approval_id 的人都能决策
- 回复通道已闭环：`normalizer.route()` 在 agent loop 之前拦截 `approve/reject <id>` 文本命令（传 `msg.user_id`）；TUI `dispatch` 的 METHOD_APPROVE 传 `conn.user_id`
- loop 仅在 `reply_func is not None` 时才进 gate（`loop.py:755`）——纯无会话路径现状本就不触发审批

设计原则：谁承担后果，谁来审批。medium = 用户自担层（知情同意），high = 系统影响层（权限授予）。

## Goals / Non-Goals

**Goals:**
- `requester` 哨兵：审批提示发回当前会话，发起人原地决策
- 决策身份校验：只有授权决策人能 resolve
- 无会话回落 default-closed；默认行为不变（哨兵须显式配置）

**Non-Goals:**
- Slack 按钮交互（Change 2：slack-approval-buttons）
- send_im_message 工具（Change 3：send-im-message-tool）
- 改变 medium/high 的默认 approvers 配置（迁移姿势：显式开启，跑稳再议默认）
- quorum 策略扩展（现状 any，不动）

## Decisions

**D1 哨兵在 `resolve_approvers` 解析层兑现，返回 `("requester", "")` 元组。**
保持返回类型 `list[tuple[str, str]]` 不变，gate 按 platform == "requester" 分流。
- 备选：在 ApprovalEntry 加独立布尔字段 `ask_requester`。否决——approvers 列表语义本就是"找谁审批"，哨兵让 requester 与外呼地址可混排（`["requester", "slack:U_ADMIN"]` = 同时问两边，先回先定），独立字段表达不了混排。

**D2 授权集合存裸 actor id，gate 内存态持有（`_authorized: dict[str, set[str]]`）。**
requester 路由存 `requester_user_id`；外呼路由存 target id（`slack:UXXX` 的 `UXXX`）。`resolve()` 校验 `approver_user_id in authorized`。调用方（normalizer 传 `msg.user_id`、TUI 传 `conn.user_id`）零改动。
- 备选：存 `platform:target` 限定串并要求调用方传平台。否决——需改两个调用方签名；裸 id 跨平台碰撞（同一 id 字符串在两平台都存在且都是审批人）概率可忽略，且碰撞后果只是放宽到"另一平台同名审批人可决策"，非提权到任意人。
- 授权集合不落库：审批本身是内存 Event 驱动、重启即 stale（`cleanup_stale_approvals` 全部 timeout），授权集合同生命周期。

**D3 requester 提示复用现有"⏳ waiting"消息位，内容升级为可操作指引。**
requester 可达时，该消息即审批提示（含 `approve <id>` / `reject <id>` 指引）；纯外呼时维持现状文案。不新增消息条数。

**D4 不可达判定：`requester` 哨兵的可达性 = `reply_func` 是否真正可用。**
gate 当前仅在 reply_func 非 None 时被调用，故哨兵在 gate 内视为恒可达；回落逻辑按"列表内其余地址继续外呼、全空 default-closed"实现，与现状一致。

## Risks / Trade-offs

- [频道内旁人冒名] requester 提示发在频道时旁人可见 approval_id → 身份校验（D2）正面拦截，旁人 resolve 返回 False 并记日志
- [身份校验破坏存量审批流] TUI / IM 文本命令调用方传的 id 与 requester/外呼 target 同源（已核实），不破坏；新增单测钉住两条路径
- [外呼审批人 id 与回复 id 不一致]（如 Slack 配的是 UXXX、回复时 msg.user_id 也是 UXXX——同源）；Telegram 同理。若未来平台出现展示名≠回复 id 的情况，授权集合按通知时的 target 记录，错配会表现为合法审批被拒（fail-closed，安全侧错）
- [requester+外呼混排时双通道竞争] 先到先定（现状 Event 语义天然如此），后到的 resolve 返回 False——可接受

## Migration Plan

- 纯增量：未配置 `requester` 的部署零行为变化；无 schema 迁移
- 身份校验对存量部署的唯一可见变化：非授权人回复 `approve <id>` 从"能批"变为"被拒"——这是修洞，记入 CHANGELOG 性质说明（决策文档）

## Open Questions

（无——按钮交互、send 工具、默认值调整均已显式划出本切片）
