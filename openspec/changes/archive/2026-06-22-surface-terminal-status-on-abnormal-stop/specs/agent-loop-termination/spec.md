## ADDED Requirements

### Requirement: 异常终止不返回空回复（给出用户可见状态）

当主循环以**异常原因**终止(`loop_detected` / `consecutive_failures` / `approval_rejected` / `cancelled`)且当前已有回复(去空白后)为空时,主循环 SHALL 返回一条**用户可见的状态回复**,说明任务已停止及其原因;对 `loop_detected` 与 `consecutive_failures`,在可得时 SHALL 附上**最后一条工具反馈/错误**(messages 中最后一条 tool 结果内容,归一化并截断)。主循环 MUST NOT 在这些异常终止下返回空回复(否则下游空回复守卫会跳过投递,导致用户静默)。

状态回复 SHALL 由确定性文本合成,MUST NOT 为此再发起一次模型调用。当已有回复非空时,既有「返回当前已有回复」语义不变(不替换)。`normal`(正常完成)、`budget_exceeded`(已有 Grace Call 兜底)、`awaiting_approval`(已发出审批提示、非终止)、`mcp_strict_unavailable`(已在入口返回明确错误)不受影响。流式(`run_stream`)与非流式(`run`)两条路径行为一致;流式在替换为状态回复时 SHALL 补发一条文本增量,使其进入最终输出。

#### Scenario: 循环检测终止且回复为空时返回状态与最后错误
- **WHEN** 主循环因 `loop_detected` 终止,且最后一条 assistant 文本为空,messages 中最后一条工具反馈为「需要 slackUserId 来定位用户」
- **THEN** 返回的回复非空,包含「已停止/重复调用未取得进展」的说明,并附上该工具反馈,提示用户换方式或补充信息

#### Scenario: 连续失败终止附最后错误
- **WHEN** 主循环因 `consecutive_failures` 终止且回复为空
- **THEN** 返回非空回复,说明连续工具失败已停止,并附最后一条工具错误

#### Scenario: 取消 / 审批拒绝给出说明
- **WHEN** 主循环因 `cancelled` 或 `approval_rejected` 终止且回复为空
- **THEN** 分别返回「任务已取消」/「操作未获批准，已取消」的用户可见说明（不附工具错误）

#### Scenario: 正常完成不受影响
- **WHEN** 主循环 `normal` 完成,或异常终止但已有非空回复
- **THEN** 返回原有回复,不替换、不附加状态文案

#### Scenario: 预算耗尽仍走 Grace Call
- **WHEN** 主循环因 `budget_exceeded` 终止
- **THEN** 仍由既有 Grace Call 产出总结回复,本要求不介入(不返回状态文案占位)
