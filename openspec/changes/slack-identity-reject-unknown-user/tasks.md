# Tasks:slack-identity-reject-unknown-user(问题 ①)

标记:`[服务器]` 需真实数据;`[本地]` 纯代码+mock 单测。

## 探针(先行,阻塞本地实现)
- [ ] [服务器] 在 `slack.py:457` 与 `:597` 各加 2 行 debug log:原始 `payload` 的 keys、`context.user_id`、最终 `slack_user_id`。
- [ ] [服务器] 重启 node;请测试同学在 alpha DM 连发"你好"+复现提示词;采集两条事件的日志;确认通过/被拒两条各自的 `slack_user_id`,定位 user 字段所在/缺失原因(及 `invalid_thread_ts` 关系)。
- [ ] [服务器] 把探针结论回填 proposal,再移除探针 log。

## 实现(TDD,test 先于 impl)
- [ ] [本地] 写测试:Assistant `user_message` payload 缺顶层 `user` 且 `context.user_id` 为空时,**不**回退成可建号的 `"unknown"`,而是拒绝/丢弃并告警(见红)。
- [ ] [本地] 实现:取不到真实 user → 走 `IMIdentityResolutionError`/丢弃路径,不伪造身份(见绿)。
- [ ] [本地] 写测试:`resolve_identity` 对空/`"unknown"` 不自动 provision;正常 platform_user_id 首次仍能建号(回归保护)(见红→绿)。
- [ ] [本地] 按探针结论修 Assistant 面板 user 提取(正确字段/线程上下文),并加测覆盖。

## 收尾
- [ ] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 部署 + 验收(同账号同 DM 多条稳定过门,不再生 `slack:unknown`)。
- [ ] [服务器] 清理历史 `slack:unknown`(43d80443)幽灵用户及其 pending(走平台 API)。
