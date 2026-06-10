# 审批分层与 Agent 主动外发：决策记录

> 2026-06-10 由张洋与 AI 协作敲定；三个 change 渐进落地：
> ① approval-requester-routing → ② slack-approval-buttons → ③ send-im-message-tool。
> 本文档随各 change 持续更新，记录设计决策与执行中遇到的问题。

## 背景

- Jira bug：AAA-8037（对话未注入用户 slack id / 发私信受阻）、AAA-8034（默认用 google mcp 发消息）、AAA-8052（缺固定频道通知）、AAA-8051（slack 按钮渲染失败）
- AAA-8037 的「id 注入」半边已由 c8297ebf（sender prefix）解决；「发私信能力」半边 + 8034/8052 根因 = `outbound.py` 原语未暴露为 agent 工具
- `permission-gate` 主 spec Purpose 原文即「medium 向请求者本人发确认、high 向预配置审批人发审批」——R1 实现未兑现 requester 一档，本批 change 将实现拉回 spec 意图

## 核心设计原则

**谁承担后果，谁来审批**：

| 层 | 本质 | 审批人 | 例子 |
|----|------|--------|------|
| medium = 用户自担层 | 知情同意（consent） | 发起用户本人（`requester`） | 替用户发消息/邮件、动用户自己的资源 |
| high = 系统影响层 | 权限授予（authorization） | 平台配置的审批人 | skill 写入、共享记忆/KB、配置变更、宿主机危险操作 |

**归层判据**：操作的写入面是否超出发起用户自己的资源域。超出 = high；不超出 = medium。
模糊地带按执行环境分级（如 run_code：沙箱内 = 用户域；裸宿主机 = 系统域）。

## Change 1：approval-requester-routing（已实现）

### 决策

- **D1 `requester` 哨兵进 `approvers` 列表**（非独立布尔字段）：与外呼地址可混排
  （`["requester", "slack:U_ADMIN"]` = 双通道通知，先回先定）。`requester:<target>`
  为保留命名空间，解析时跳过（防伪造外呼平台）。
- **D2 决策身份校验（补洞）**：gate 内存态记录每个 pending 审批的授权决策人集合
  （requester 路由 = 发起人 id；外呼路由 = 实际通知到的审批人，存裸 target 与
  `platform:target` 两种形态兼容 IM 裸 id 与既有限定串 actor）。`resolve()` 拒绝
  集合外身份：返回 False、pending 保持、记 warning。**这同时修复了既有弱点**：
  原实现任何拿到 approval_id 的人都能批。
- **D3 requester 提示复用「⏳ 等待中」消息位**：升级为含 `approve <id>` 指引的
  可操作提示，不增加消息条数。
- **D4 无会话回落**：loop 仅在 reply_func 可用时进 gate，故哨兵在 gate 内恒可达；
  列表内其余外呼地址照常通知；全部不可达 → default-closed 拒绝（现状语义）。
- **迁移姿势**：默认行为不变，`requester` 须显式配置。存量部署唯一可见变化 =
  非授权人回复 approve 从「能批」变为「被拒」（修洞，安全侧）。

### 执行中问题与解决

- **测试假绿陷阱**：身份校验测试最初把断言写在 `asyncio.create_task` 的协程里——
  任务内异常不传播，断言被吞、测试假绿。重构为协程收集结果列表、测试主体断言。
  （教训：并发测试的断言必须落在主协程。）

## Change 2：slack-approval-buttons（待实施）

- 审批提示 Block Kit 化：描述 + 内容预览 + [批准][拒绝][始终允许] 按钮
- Socket Mode `app.action` 处理点击；点击者身份取自 Slack 事件（比文本命令更可靠），
  过 Change 1 的授权校验；`chat.update` 写结果态防重复点击
- 文本命令 `approve/reject <id>` 保留（Telegram/TUI/降级）

## Change 3：send-im-message-tool（待实施）

- 内置 `send_im_message(target, text, target_type)`，注册 medium，复用
  `outbound.send_to()`；`ToolContext` 扩展携带 `outbound_connectors` + 会话元数据
- 发当前会话对象（发件人 DM / 当前频道）= 直接执行；第三方 = 走 gate
- 关单映射：AAA-8037②、AAA-8034、AAA-8052 根因；AAA-8051 由 Change 2 解决基础设施层
