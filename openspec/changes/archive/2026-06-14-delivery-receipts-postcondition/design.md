# Design — delivery-receipts-postcondition

## Context

AAA-8050 的本质：任务完成判据是模型自述，不是系统事实。事故中 `gws gmail +send --draft` 把带附件邮件存成草稿、send_file 从未被调用，模型仍打勾"全部完成"。投递面已收敛到 `outbound.send_to` / `send_file_to`（工具、生成图上传、cron fire 共用），但只返回 bool、不留痕。trace-tool-spans 落地后 tool 级事件可查，但"工具被调了"≠"投递成功了"（且 MCP 外发完全在 fleetent 原语之外）——需要投递维度自己的事实链。

## Goals / Non-Goals

**Goals:**

- 每次经 fleetent outbound 原语的投递尝试有结构化回执（成败、目标、kind、平台凭证 ts/file_id）。
- 回执三处可见：run 级台账（进程内）、traces（审计）、用户侧事实尾注（实时对账）。
- 尾注是确定性系统输出：有出站尝试才出现，模型不可改写，零尝试零噪音。

**Non-Goals:**

- 审查/改写模型的成功声明文本（NLU 判别"是否虚报"不可靠，方向放弃——用并列事实替代审查）。
- MCP 第三方工具外发的回执（协议外不可证实；trailer 不为其背书即是治理）。
- 投递重试/补偿机制；平台侧回执 UI。

## Decisions

### D1 回执对象替代 bool

`DeliveryReceipt{ok, platform, target, target_type, kind, thread, provider_ref(ts/file_id), error}`。`send_to`/`send_file_to` 返回回执；同仓调用方一次性收敛（bool 语境改判 `receipt.ok`）。备选：旁路全局收集器（保持 bool 返回）——隐式全局可变状态，repo 风格反对，否决。

### D2 run 级台账挂在 ToolContext/run state

run 入口创建空台账，outbound 原语经注入的记录器（或 tool_context 透传）追加回执；cron fire 路径在 `_fire` 内自建台账。备选：contextvar——跨 task 语义脆弱（并行 dispatch），显式传递更直白。

### D3 trace 事件

每条回执写 `event_type="delivery"`（payload=回执字段，target 经脱敏基线），复用 trace-tool-spans 的记录 API 与失败隔离语义（写失败仅 warning）。

### D4 尾注生成与注入点

run 收尾、最终回复确定后：台账非空 → 由台账确定性渲染一行尾注，追加到回复文本之后（reply_func 发送前拼接；流式路径在末帧后追加）。格式紧凑：`📬 实际投递：文件 N（明细…）；消息 M（明细…）；失败 K（原因…）`。台账为空 → 不追加。模型在提示词中不被告知尾注存在（防止其模仿/伪造同款行文——尾注总在最后且由系统拼接，伪造的会被真尾注跟随暴露）。

### D5 与既有 spec 的边界

工具结果文本（"已把文件发送给…"）继续由工具自产、语义不变——回执是其数据来源的结构化化，不新增工具 requirement；`scheduled-task-delivery` 的 best-effort/last_error 语义不变，仅内部改读回执。

## Risks / Trade-offs

- [尾注打扰极简对话] → 仅出站尝试非空才出现；单行紧凑格式。
- [流式路径追加时序] → 末帧后单独一条 reply 发送尾注（与既有 EGRESS 提示同款模式），不插入流中。
- [bool→回执波及面] → 调用方集中（builtin 两工具、上传原语、cron、permission_gate 通知），一次 change 内收敛 + mypy 把关。
- [模型学会复述尾注样式] → 真尾注永远由系统在最后追加；重复无害，缺失（模型声称发了而真尾注说 0）即暴露。

## Migration Plan

纯增量行为；回滚 = 停止追加尾注与 delivery 事件，回执对象保留（内部 API）。

## Open Questions

- 无。
