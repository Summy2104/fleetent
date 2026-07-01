# Tasks:approval-command-tolerate-text-mention(问题 ③)

标记:`[本地]` 纯代码+单测;`[服务器]` 真实 Slack 验收。

## 实现(TDD,test 先于 impl)
- [x] [本地] 写测试:`_match_approval_command("@R. Alpha approve 00b0691a")` 应命中(见红)。
- [x] [本地] 实现:剥离前导纯文本 @token / bot 显示名后再匹配(见绿)。
- [x] [本地] 写测试矩阵(回归):命中 = `approve <id>` / `<@U…> approve <id>` / `@R. Alpha approve <id>` / `reject <id>` / `approve always <id>`;不命中 = `@bot approve the plan` / `approve` / `approve xyz`(非法 id)。

### ③补丁(真机验收发现:id 带 markdown 格式)
- [x] [本地] 写测试:``approve `5a6decf1` `` / ` ```5a6decf1``` ` / `approve **5a6decf1**`（含 mention 组合)都命中(见红→绿)。
- [x] [本地] 实现:`_match_approval_command` 匹配前用 `_MD_FORMAT_RE` 剥掉反引号/星号(id 不含这些字符,散文仍不误命中)。

## 收尾
- [x] [本地] `make test-pr` 全绿(并跑 `make test-integration-ci` 全绿)。
- [x] [服务器] 部署 + 真实 Slack 验收(三种写法 + 带反引号的 `approve `<id>`` 都 resolve 并送达,不再刷新 ID)。
