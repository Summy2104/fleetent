# Tasks:approval-command-tolerate-text-mention(问题 ③)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收。

## 实现(TDD,test 先于 impl)
- [ ] [本地] 写测试:`_match_approval_command("@R. Alpha approve 00b0691a")` 应命中(见红)。
- [ ] [本地] 实现:剥离前导纯文本 @token / bot 显示名后再匹配(见绿)。
- [ ] [本地] 写测试矩阵(回归):命中 = `approve <id>` / `<@U…> approve <id>` / `@R. Alpha approve <id>` / `reject <id>` / `approve always <id>`;不命中 = `@bot approve the plan` / `approve` / `approve xyz`(非法 id)。

## 收尾
- [ ] [本地] `make test-pr` 全绿。
- [ ] [服务器] 部署 + 真实 Slack 验收(三种写法都 resolve 并送达,不再刷新 ID)。
