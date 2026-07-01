# Tasks:managed-approval-button-wire-statedb(问题 ②)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收 + 数据清理。

依赖:建议在变更 ③(approval-command-tolerate-text-mention)落地后做,方案 A 复用其命令路径。

## 实现(TDD,test 先于 impl)— 采用方案 A
- [x] [本地] 写测试:node 收到 `block_actions`(approval_approve/reject/approve_always)时,合成对应 `approve/reject [always] <id>` 指令,经 `/im/route` 转发链交 agent 处理(见红)。
- [x] [本地] 实现:`handle_approval_action`(或其 node 侧调用点)改为转发而非就地 `get_approval`/resume;注入由 node 提供(不让 `im_gateway` import `node`)(见绿)。(经 `inbound_dispatch.get_inbound_dispatcher()` 检测 node 注入,有则 `_forward_approval_decision` 合成命令走 dispatcher;护栏 `check_module_boundaries` 绿。)
- [x] [本地] 写测试:standalone(agent 自托管)审批按钮路径不回归(仍能就地 resolve)。(既有 6 个测试覆盖就地 resolve/chat_update/ephemeral/resume,全绿。)
- [x] [本地] 写测试:点击后 `ack()` 仍先发、prompt 被更新为结果态(防重复点击)。(`test_managed_button_forwards_synthesized_command` 断言 `ack` 先发 + `chat_update(blocks=[])`。)

### ②补丁(真机验收发现:授权用了 Slack id 而非 uuid + 乐观 UI 谎报)
- [x] [本地] (a) 转发前经 `resolve_identity` 把 clicker 的 Slack id 解析成内部 uuid(与入站一致),合成 msg 用 uuid → agent 授权匹配 requester;解析失败(`IMIdentityResolutionError`)则不转发 + ephemeral 提示。测试 `test_managed_button_resolves_clicker_slack_id_to_uuid` / `..._unresolved_identity_not_forwarded`。
- [x] [本地] (b) 去掉乐观"已批准":方案A 下授权在 agent 侧异步判定,node 改为中性"⏳ 已提交审批…(移除按钮防重复点)";真结果由 agent 投递(成功→resume 送达;失败→route() unauthorized 回执)。测试 `test_managed_button_ui_does_not_claim_approved_before_resolve`。

## 收尾
- [x] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 部署 + 真实 Slack 验收(三种按钮均 resolve+resume+送达,无 `state_db not initialized`)。
- [ ] [服务器] 清理历史卡住 pending(00b0691a / f758a7a7 / 8eafa231 / 305c9a87,走平台 API)。
