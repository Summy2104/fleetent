# Tasks:slack-identity-reject-unknown-user(问题 ①)

标记:`[服务器]` 需真实数据;`[本地]` 纯代码+mock 单测。

## 探针(先行,阻塞本地实现)
- [x] [服务器] 在 `slack.py:457` 与 `:597` 各加 2 行 debug log:原始 `payload` 的 keys、`context.user_id`、最终 `slack_user_id`。
- [x] [服务器] 重启 node;采集事件日志。结论:上下文正常时 payload 有 user、解析正确;上下文坏(`invalid_thread_ts`)时 `context.user_id=None`、payload 也可能没 user → 回退 `"unknown"` → 自动建号(`slack:unknown` 幽灵)→ 不在 allow_users → `_REJECTION_MSG`。
- [x] [服务器] 把探针结论回填 proposal,再移除探针 log。(探针 debug log 已从 slack.py 移除,仅保留意图内的 `slack_identity_resolution_rejected` 告警。)

## 实现(TDD,test 先于 impl)
- [x] [本地] 写测试:Assistant `user_message` payload 缺顶层 `user` 且 `context.user_id` 为空时,**不**回退成可建号的 `"unknown"`,而是拒绝/丢弃并告警(见红)。(`test_assistant_route_discards_event_without_user`)
- [x] [本地] 实现:取不到真实 user → 走 `IMIdentityResolutionError`/丢弃路径,不伪造身份(`slack.py:457/597` 的 `or "unknown"` 改 `or ""`)(见绿)。
- [x] [本地] 写测试:`resolve_identity` 对空/`"unknown"` 不自动 provision;正常 platform_user_id 首次仍能建号(回归保护)(见红→绿)。(`_NON_REAL_IM_IDENTITIES` 在调注入 resolver 之前拒绝;`test_resolve_identity_rejects_unknown_*`)
- [x] [本地] (best-effort·主动推迟)按探针结论修 Assistant 面板 user 提取(正确字段/线程上下文)。当前 (a)(b) 已满足验收(无 user 事件被拒、不建幽灵、正常用户不受影响);进一步"从坏上下文里救回 user"需确切的坏 payload 形状,留待有样本再做。

## 收尾
- [x] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [x] [服务器] 部署 + 验收(同账号同 DM 多条稳定过门,不再生 `slack:unknown`)。
- [x] [服务器] 清理历史 `slack:unknown`(43d80443)幽灵用户及其 pending(走平台 API)。
