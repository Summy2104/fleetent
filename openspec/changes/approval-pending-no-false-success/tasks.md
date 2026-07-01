# Tasks:approval-pending-no-false-success(问题 ⑤,最高优先级)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收。

## 实现(TDD,test 先于 impl)
- [ ] [本地] 写测试:工具返回 `awaiting_human_approval` 挂起后,会话再来一条非审批命令(如「同意」/「好的」),agent **不**重新调用工具成功、**不**捏造投递 receipt、**不**输出"已发送成功"(见红)。
- [ ] [本地] 实现:挂起工具的 tool_result 文案改为硬约束("尚未执行,未获批前严禁声称完成");pending 期间每轮注入强提示(见绿)。
- [ ] [本地] 写测试:pending 期间续轮输出应是"仍待审批 + 如何 approve"的指引,而非完成态(见红→绿)。
- [ ] [本地] 写测试(回归):真实 approve(命令路径)后,工具执行并拿到 receipt,才允许报成功。

## 收尾
- [ ] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 真实 Slack 验收:发→挂起→回「同意」→ agent 必须说仍待审批(不报成功);approve 后才送达并报成功。
