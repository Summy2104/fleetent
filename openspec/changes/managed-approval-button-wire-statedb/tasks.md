# Tasks:managed-approval-button-wire-statedb(问题 ②)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收 + 数据清理。

依赖:建议在变更 ③(approval-command-tolerate-text-mention)落地后做,方案 A 复用其命令路径。

## 实现(TDD,test 先于 impl)— 采用方案 A
- [ ] [本地] 写测试:node 收到 `block_actions`(approval_approve/reject/approve_always)时,合成对应 `approve/reject [always] <id>` 指令,经 `/im/route` 转发链交 agent 处理(见红)。
- [ ] [本地] 实现:`handle_approval_action`(或其 node 侧调用点)改为转发而非就地 `get_approval`/resume;注入由 node 提供(不让 `im_gateway` import `node`)(见绿)。
- [ ] [本地] 写测试:standalone(agent 自托管)审批按钮路径不回归(仍能就地 resolve)。
- [ ] [本地] 写测试:点击后 `ack()` 仍先发、prompt 被更新为结果态(防重复点击)。

## 收尾
- [ ] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 部署 + 真实 Slack 验收(三种按钮均 resolve+resume+送达,无 `state_db not initialized`)。
- [ ] [服务器] 清理历史卡住 pending(00b0691a / f758a7a7 / 8eafa231 / 305c9a87,走平台 API)。
