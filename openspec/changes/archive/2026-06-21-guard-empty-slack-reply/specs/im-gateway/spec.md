## ADDED Requirements

### Requirement: Empty replies are not posted

回复投递在文本去空白后为空**且**没有 blocks 时 SHALL 跳过——MUST NOT 以空文本调用 Slack `chat.postMessage`（Slack 以 `no_text` 拒绝并把异常冒泡到 listener，中断回复/审批投递）。当文本去空白后非空，或存在 blocks（含 blocks-only 的空文本消息）时,投递照常进行。跳过空投递 SHALL NOT 影响既有的状态指示清除（思考指示器照常消失）。该守卫位于 IM 适配器（Slack）侧,覆盖所有回复路径（assistant 面板 / 频道 @mention / 审批动作恢复）。

#### Scenario: 空文本回复被跳过
- **WHEN** agent 某回合产出空（或纯空白）文本、且无 blocks,经任一回复路径投递
- **THEN** 适配器不调用 Slack `chat.postMessage`,不产生 `no_text` 错误,listener 不中断

#### Scenario: 非空文本正常投递
- **WHEN** agent 产出非空文本回复
- **THEN** 适配器照常作为线程回复投递该文本

#### Scenario: blocks-only 消息仍投递
- **WHEN** 回复文本为空但带有 blocks
- **THEN** 适配器照常投递该消息（blocks 即可投递,不触发跳过）

#### Scenario: 跳过空投递不影响状态清除
- **WHEN** 一次空文本回复被跳过
- **THEN** 该路径既有的状态指示清除（`setStatus("")`）照常执行,思考指示器消失
