## Why

`send_im_message` 的既定本意是「对**其他**用户/频道主动外发」,回复当前对话应走纯文本(由 harness 的 `say()`/`reply_func` 自动投递)。但当前实现对「目标 = 当前对话发起人/频道」的调用**仍然投递**(self-DM 还 pin 到频道),只是免审批。于是当模型(尤其能力较弱或被「回复要@我」之类指令带偏的模型)既调 `send_im_message` 发当前会话、又正常产出最终回复时,**同一内容被投递两次**(工具发一次 + harness 回一次),线上已观测到一条用户消息触发 2–3 条重复投递。

## What Changes

- `send_im_message` 在**目标解析为当前对话**(同一 DM 用户或同一频道,即 `approval_policy.risk_for` 判为 `none`)时,**不再投递**,而是返回一句无投递的引导文案(提示"回复当前对话直接输出文本即可,本工具仅用于发给其他用户/频道")。当前会话的回复由 harness 的最终文本投递负责,工具侧不再产生重复。
- 因此移除原「channel self-DM pin 到频道并投递」的行为——该场景正是"发给当前会话发起人",现统一 no-op。
- **对第三方**(目标 ≠ 当前对话)的外发**完全不变**:照常 medium 审批、照常投递、`files` 附件逻辑不变。
- 工具 docstring 保持"仅用于对外"的定位(已是如此),无需改语义。

## Capabilities

### Modified Capabilities
- `builtin-outbound-tool`:`send_im_message` 在目标=当前对话时由「pin 投递(none)」改为「no-op + 引导(none)」;第三方外发不变。

## Impact

- **owning package**:`tools/`(`builtin_tools.send_im_message`)。复用 `governance/approval_policy.risk_for` 的当前会话判定,无新依赖。
- **public API surface**:`send_im_message` 签名不变;当前会话调用的**返回语义**由"已投递"变为"未投递+引导"(行为变更,需在 spec 声明)。
- **owned tables / config / migration**:无。
- **cross-module dependencies**:`tools` → `governance.approval_policy`(既有依赖),零 `fleetent.platform.*` import。
