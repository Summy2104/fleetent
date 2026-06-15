## Why

审批批准后续跑的**最终回复（含「📬 实际投递」回执）没回到原对话**：频道里落到频道**顶层**（非原 thread），私信里**另开一个会话**回复。用户无法在发起处看到结果。

根因：`im_gateway.normalizer._resume_pending_in_session` 正确地从持久化 `address` 重建了地址版 `reply_func`（line 366）并交给续跑 loop.run，但 `loop.run` 只用 reply_func 发审批 prompt、**最终回复是返回值**。该返回值由调用方 post：文本路径 `normalizer.route` 用 **approve 命令消息的 `msg.reply_func`**、按钮路径 `slack.py` 用按钮频道的 `_reply` —— 二者都是**审批动作触发处**的投递器，而非持久化对话地址。故最终回复落到触发处（频道顶层 / 新 DM）。这违反 approval-suspend-resume「resumed output 落原 chat/thread」的既有不变量（仅工具投递与 prompt 遵守，最终回复未遵守）。

## What Changes

- `_resume_pending_in_session` 自己用**地址版 `reply_func`**（无地址时回退触发处，保持降级语义）投递续跑最终回复，并仍返回该回复（供日志/测试）。
- 两个调用方不再二次 post：`normalizer.route`（文本 approve）与 `slack.py`（按钮）删除对返回值的 `msg.reply_func(reply)`/`_reply(reply)`。
- 净效果：频道→回原 thread、私信→回原 DM 会话，与工具投递/审批 prompt 同址；「📬 实际投递」回执随之回到正确对话。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `approval-suspend-resume`: 明确恢复路径**自身**经持久化地址投递续跑最终回复；解析触发处的 reply_func MUST NOT 用于投递该最终回复（消除最终回复落到频道顶层/新 DM 的偏差）。

## Impact

- `src/fleetent/im_gateway/normalizer.py`：`_resume_pending_in_session` 末尾经地址版 reply_func 投递最终回复；`route` 文本-approve 分支不再二次 post。
- `src/fleetent/im_gateway/slack.py`：按钮分支不再二次 post。
- 测试：`tests/integration/test_resume_address_contract.py` 新增「最终回复落持久化地址、不走触发处 reply_func」；既有无地址降级用例不变。
- 无数据迁移/config/owned table 变更；不改审批触发面、风险分级或回执渲染本身（#265）；只修最终回复的投递目标。
