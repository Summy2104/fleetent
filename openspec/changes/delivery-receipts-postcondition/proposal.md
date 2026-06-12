# delivery-receipts-postcondition

## Why

复杂任务失败会被虚报成成功（Jira AAA-8050）：2026-06-12 实测中模型最终汇报"邮件发送 ✅ / Slack 消息发送 ✅"，而实际文件从未上传、带附件邮件停在草稿——系统层面没有任何机制把"宣称已投递"与"真实投递事实"对账，模型自述即结果。投递走 `outbound` 原语（send_to / send_file_to）只返回 bool，无回执记录；用户拿不到任何系统背书的投递清单，谎报不可见、事后不可审计。

## What Changes

- **outbound 原语产生投递回执**：`send_to` / `send_file_to` 成功时返回回执 `{platform, target, target_type, kind(text|file), thread, ts/file_id?}`，失败返回失败回执（含原因）；保持永不抛的既有语义。
- **run 级回执台账**：一次 run 内经 outbound 原语的全部投递尝试（send_file / send_im_message / 生成图上传 / cron fire 投递）记入 run 作用域台账，并以 `delivery` trace 事件落 traces（复用 trace-tool-spans 底座）。
- **事实投递尾注（delivery trailer）**：当一次 run 存在**至少一次出站投递尝试**时，最终回复后附加一行系统生成的事实尾注——成功/失败清单（如 `📬 实际投递：文件 1（slack:U…，✅）；消息 1（✅）` / `📬 实际投递：文件 0——send_file 未被调用`）。模型不可改写该尾注；零出站尝试的 run 不加尾注（避免噪音）。虚报不再靠审查模型文本，而是把地面真相摆在模型声明旁边。
- **范围界定**：回执只覆盖 fleetent 自身 outbound 原语；MCP 第三方工具的外发（如 gws 邮件）不可回执，trailer 不为其背书（这正是它的价值：模型声称"邮件已发"而 trailer 只列 fleetent 可证实的投递，差异即暴露）。

## Capabilities

### New Capabilities

- `delivery-receipts`: outbound 回执、run 级投递台账与 trace 落库、最终回复的事实投递尾注。

### Modified Capabilities

（无——`builtin-outbound-tool` / `sandbox-file-send` 的工具结果文本语义不变；回执在 outbound 层与 loop 收尾生效，不改工具 requirement。）

## Impact

- **代码**：`outbound.py`（返回值 bool → 回执对象，调用方兼容收敛）；`runtime/loop.py` 或 normalizer 收尾（trailer 注入）；`observability/traces.py`（delivery 事件，复用 trace-tool-spans API）；`cron_scheduler._deliver`（回执记录）。
- **owned tables**：无新表（traces 复用）。
- **config namespace**：无。
- **依赖方向**：runtime / im_gateway → outbound / observability（既有方向），零 platform import。
- **依赖序**：在 `trace-tool-spans`（回执事件底座）与 `unified-file-exchange`（send 工具共享投递内核）之后实施；与 `conversation-address-unification` 正交（trailer 经 replier 发送自然落原 thread）。
- **兼容性**：outbound 返回值变更为内部 API（调用方同仓收敛）；trailer 为增量用户可见行为。
