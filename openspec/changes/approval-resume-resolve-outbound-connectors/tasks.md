# Tasks:approval-resume-resolve-outbound-connectors(问题 ⑥,核心)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收。

## 实现(TDD,test 先于 impl)
- [ ] [本地] 写测试:`is_node_managed_runtime()` 为真时,经 `_resume_pending_in_session` 构造的 `ToolContext.outbound_connectors` 含各 managed 平台的 `ManagedOutboundConnector`(当前为空 → 见红)。
- [ ] [本地] 实现:`_resume_pending_in_session` 在建 `ToolContext` 前 `resolve_for_runtime(agent.name if agent else None, msg.outbound_connectors)`,并用解析结果建 `make_replier`/`make_uploader`/`ToolContext`(见绿)。
- [ ] [本地] 写测试:standalone(`msg.outbound_connectors` 非空)路径不变 —— resolve 直接返回原连接器(回归)。
- [ ] [本地] 写测试:resume 的 `send_im_message` 在 managed 下走 enqueue 而非"无连接器"失败(可 mock `ManagedOutboundConnector.send_to`/enqueue,断言被调用)。

## 收尾
- [ ] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 真实 Slack 验收:发 → 审批 → 批准后程鑫**真的收到**;检查 node `im_outbound_queue` 出队投递记录。
