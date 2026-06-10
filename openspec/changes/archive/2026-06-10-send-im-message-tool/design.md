## Context

现状（已核实）：

- `outbound.send_to / is_reachable` 原语成熟（审批门、调度器在用），未注册为工具
- `ToolContext`（registry.py）是 out-of-band 注入通道：工具声明 `tool_context` 参数即接收，永不进 LLM schema；现有字段 agent_name / features / session_id / session_context
- `loop.run()`（IM 路径）签名已有 `outbound_connectors`；两处 `ToolContext(...)` 构造点都在其作用域内；`run_stream()`（TUI/HTTP 路径）**没有**该参数
- loop 注释明确：「the tool's registry risk (never LLM args — anti-escape)」——风险等级是静态注册属性，不得由 LLM 参数派生

## Goals / Non-Goals

**Goals:**
- agent 可经统一治理（medium 审批）主动给 IM 用户发 DM / 向频道发消息
- 平台默认取当前会话；连接器经 ToolContext 注入，工具自身零全局状态

**Non-Goals:**
- TUI/HTTP 路径的外发支持（run_stream 无连接器来源；后续需要时再立切片）
- 附件/blocks 富消息发送（文本先行；AAA-8035 附件稳定性另案）
- 定时任务场景的工具化外发（cron 投递已有专用路径）

## Decisions

**D1 连接器经 `ToolContext.outbound_connectors` 注入，不引模块全局。**
与 session_context 同模式：loop 持有 → ToolContext 透传 → 声明参数的工具接收。工具在 connectors 为空（run_stream 路径 / 测试裸调）时返回明确错误文本，不抛异常。
- 备选：模块级注册表存活动连接器。否决——全局可变状态（Forbidden Pattern），且破坏多 agent 进程隔离。

**D2 全量 medium 门控，放弃"当前会话目标直发"分流（修正脑暴方案 C）。**
两个理由：① 给当前会话发消息 = reply 既有能力，agent 无需工具即可做到；工具的边际能力恰是"发给第三方/跨频道"，对这部分全量门控在概念上就是对的。② 按目标分流要求执行处置依赖 LLM 提供的 `target` 参数，触碰 loop「risk 永不取自 LLM 参数」的 anti-escape 设计红线；为一个 reply 已覆盖的场景开这个口不值。配合 Change 1/2（requester 路由 + 按钮），审批成本 = 一次点击。

**D3 `platform` 参数可选，默认当前会话平台（取自 `session_context.platform`）。**
单平台部署 LLM 无需关心平台概念；跨平台外发（Slack 会话里发 Telegram）显式传参即可。

**D4 失败语义 = 返回解释性文本，不抛异常。**
不可达 / 无连接器 / 发送失败分别返回不同的中文说明（LLM 可据此向用户解释或换方案）；与 builtin 工具既有惯例一致（如 invoke_agent 的 "agent not found"）。

## Risks / Trade-offs

- [滥用面] agent 可向任意可达用户发消息 → medium 审批 + allowed_tools 白名单双闸；审批提示含目标与内容预览（tool_args 进审批记录）
- [run_stream 路径静默无能力] TUI 用户调用得到"当前通道不支持"文本 → 明确告知而非静默失败
- [Telegram 可达性约束]（用户须先 /start 过 bot）→ 复用 is_reachable 预检，不可达即返回说明

## Migration Plan

纯增量：新工具默认不在任何 agent 的 `allowed_tools` 里（白名单制），加入白名单 + 配置 approval_routing 后生效。无 schema/配置迁移。

## Open Questions

（无）
