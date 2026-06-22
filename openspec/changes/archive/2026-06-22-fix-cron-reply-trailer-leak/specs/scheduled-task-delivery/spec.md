## MODIFIED Requirements

### Requirement: SILENT reply suppresses delivery

When the agent's final reply for a fired task is the sentinel `[SILENT]`, the system SHALL record the run as successful (`last_status="ok"`) but SHALL NOT deliver any message to the user.

触发任务的 run 输出 MUST NOT 携带面向操作者的投递回执 trailer(`📬 实际投递…`):该回执是为**交互式对话**确认投递而设计的,定时任务在触发时无交互对象,其回复是要广播的通知正文。因此 fired-run 的回执 trailer SHALL 被抑制,使广播正文与 `[SILENT]` 哨兵保持干净(不含操作者向说明)。

静默判定 SHALL 对尾随内容(回执 trailer、空白等)鲁棒:当回复的首个非空行 strip 后等于 `[SILENT]`(或回复为 None / 空白)时,即视为静默并跳过投递——即使其后被追加了其它内容,也不得因此把哨兵广播出去。IM 交互路径(非定时任务)的投递回执不受影响。

#### Scenario: Silent run delivers nothing
- **WHEN** a fired task's agent reply is `[SILENT]`
- **THEN** the run is recorded ok and no message is delivered to the user

#### Scenario: 带回执的静默回复仍跳过投递
- **WHEN** fired-run 内发生过投递(台账非空),若 run 未抑制回执则回复会变成 `[SILENT]\n\n📬 实际投递：消息 1（U0…）`
- **THEN** 投递判定仍将其识别为静默(首行 == `[SILENT]`)并跳过,绝不把 `[SILENT]` 或回执广播给用户

#### Scenario: fired-run 广播正文不含操作者回执
- **WHEN** 一个非静默的 fired task 在 run 内调用了 send_im_message/send_file（台账非空），最终回复为通知正文
- **THEN** 广播到目标的内容为干净的通知正文,MUST NOT 追加 `📬 实际投递…` 操作者回执

#### Scenario: 交互式 IM 投递回执不受影响
- **WHEN** 普通(非定时任务)IM 对话中 agent 调用 send_im_message/send_file 并投递成功
- **THEN** 该交互回复照常携带 `📬 实际投递…` 回执(默认行为不变)
