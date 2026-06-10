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

## Change 2：slack-approval-buttons（已实现）

### 决策

- **D1 Block Kit 渲染助手放 `outbound.py`**（`approval_prompt_blocks`）：governance 不感知
  Slack 结构、只透传 opaque payload；outbound 本就承载 Slack API 细节，是平台渲染知识的归属地
- **D2 能力探测降级**：gate 调 `reply_func(text, blocks=...)`，文本-only 通道（Telegram/TUI）
  抛 TypeError → 纯文本重发。零侵入，旧适配器与测试 mock 自然兼容
- **D3 三个独立 action_id**（`approval_approve` / `approval_reject` / `approval_approve_always`），
  value 携带 approval_id；`^approval_` 前缀单处理器注册
- **D4 点击反馈**：成功 → `chat.update` 原消息为结果态（含决策人）并清空按钮（防重复点击）；
  非授权/过期 → `chat_postEphemeral` 仅点击者可见提示，原提示保持。点击者身份取自交互
  payload 的 `body.user.id`（比文本命令更可靠），过 Change 1 授权校验
- **D5 `send_to` 增可选 `blocks` 参数**：Slack DM/频道路径透传（text 保留作通知 fallback），
  Telegram 忽略；签名向后兼容
- 文本命令 `approve/reject <id>` 全平台保留（按钮与文本双轨，先到先定，gate 幂等兜底）

### 部署要求

- **Slack App 必须开启 Interactivity**（App 设置 → Interactivity & Shortcuts）。Socket Mode
  下 block_actions 走现有连接，无需公网回调 URL。未开启时按钮显示但点击无响应——文本命令
  仍可用作兜底

## Change 3：send-im-message-tool（已实现）

### 决策

- **D1 连接器经 `ToolContext.outbound_connectors` 注入**（与 session_context 同模式）：
  `loop.run()`（IM 路径）填充；`run_stream()`（TUI/HTTP 路径）无连接器来源，工具返回
  「当前通道不支持主动外发」说明文本。不引模块全局状态（Forbidden Pattern）
- **D2 设计修正：放弃脑暴方案 C 的"当前会话目标直发"分流，全量 medium 门控**。
  实施时发现 loop 有明确 anti-escape 红线：「risk 永不取自 LLM 参数」——按 target
  分流处置违反该设计。且细想后分流本无必要：给当前会话发消息 = reply 既有能力
  （agent 不需要工具就能回复），工具的边际能力恰是"发给第三方/跨频道"，对它全量
  门控概念正确。配合 Change 1/2，审批成本 = 一次按钮点击
- **D3 `platform` 参数可选**，默认当前会话平台（session_context.platform）；跨平台
  外发显式传参
- **D4 失败语义 = 解释性文本不抛异常**（无平台/无连接器/不可达/发送失败各有专属
  文案），沿 builtin 工具惯例
- 启用条件：agent 的 `allowed_tools` 含 send_im_message + approval_routing 配置
  medium 审批人（推荐 `requester`）

### 关单映射

- AAA-8037②（发私信能力）、AAA-8034（默认用 google mcp 根因）、AAA-8052（固定频道
  通知）由本 change 关闭根因；AAA-8051（按钮渲染）由 Change 2 解决基础设施层

## 执行记录补充（2026-06-10 晚）

- **my-bot smoke**：工具链路端到端验证通过（agent 经 send_im_message 成功投递 DM）。
  首轮未触发审批是因 my-bot 此前配置 `permission_gate_enabled: false`（本地跳审批的
  历史配置）——gate 行为正确，已改回 true 并配置 `approval.by_risk.medium.approvers:
  ["requester"]`。第二轮按钮交互验证因用户同时在实机测试（定时通知）而中止，避免
  干扰；按钮点击留待真人体验验证
- **发现的预存 bug（上报，不在本批修复）**：`cron_scheduler._parse_cron` 对
  `schedule_kind='run_at'`（一次性任务，cron_expr=NULL）在启动恢复时直接 `expr.split()`
  崩溃，导致 agent 无法启动。本地以删除过期任务行恢复。归属 AAA-8039 定时任务一族，
  建议 owner 修复：`_parse_cron` 前按 schedule_kind 分流或对 None 容错
