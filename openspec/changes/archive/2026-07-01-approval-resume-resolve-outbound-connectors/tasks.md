# Tasks:approval-resume-resolve-outbound-connectors(问题 ⑥,核心)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收。

## 实现(TDD,test 先于 impl)
- [x] [本地] 写测试:`is_node_managed_runtime()` 为真时,经 `_resume_pending_in_session` 构造的 `ToolContext.outbound_connectors` 含各 managed 平台的 `ManagedOutboundConnector`(当前为空 → 见红)。
- [x] [本地] 实现:`_resume_pending_in_session` 在建 `ToolContext` 前 `resolve_for_runtime(agent.name if agent else None, msg.outbound_connectors)`,并用解析结果建 `make_replier`/`make_uploader`/`ToolContext`(见绿)。
- [x] [本地] 写测试:standalone(`msg.outbound_connectors` 非空)路径不变 —— resolve 直接返回原连接器(回归)。
- [x] [本地] 写测试:resume 的 `send_im_message` 在 managed 下走 enqueue 而非"无连接器"失败。(经 `test_resume_managed_runtime_resolves_managed_connectors` 断言 resume 的 `tool_context.outbound_connectors["slack"]` 是 `ManagedOutboundConnector`(agent_name 正确)——`connectors.get("slack")` 不再为 None,即不会命中"无连接器"分支;`ManagedOutboundConnector` 的 enqueue 行为由其自有测试覆盖。)

## 收尾
- [x] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [x] [服务器] 真实 Slack 验收:发 → 审批 → 批准后程鑫**真的收到**;检查 node `im_outbound_queue` 出队投递记录。
