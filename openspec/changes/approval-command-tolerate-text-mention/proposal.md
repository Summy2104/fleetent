# 变更:approve/reject 文字命令容忍纯文本 @名字前缀(消除审批死循环)

母文档:`docs/records/aaa-8204-recovery.md`(问题 ③)

## 为什么

手动 `approve <id>` 出现审批死循环:每 approve 一次,bot 反而新发起请求并生成新 Approval ID(实测 `00b0691a → e0862acb → 4a5c0e85`),消息始终发不出。

根因:审批命令拦截在 `route()`(`src/fleetent/im_gateway/normalizer.py:477-532`)靠 `_match_approval_command` 识别,它先用 `_strip_leading_mention` 去掉一个前导提及。但该正则 `_LEADING_MENTION_RE = ^\s*<@[^>]+>\s*`(`:23`)**只剥真正的 Slack 提及 `<@id>`**。在 DM / Assistant 面板里用户打的 `@R. Alpha` 是**纯文本**,剥不掉 → `^(approve|reject)…` 不匹配 → 命令漏进 agent 主循环,LLM 当普通话("好的,已收到批准指令,让我重新发起")重新调 `send_im_message` → 又撞门 → 新 ID。

实测(安装版 `_match_approval_command`):`approve 00b0691a`✅、`<@U…> approve 00b0691a`✅、`@R. Alpha approve 00b0691a`✗。

> 注:命中后的 resume(`approval_resume.py:102`)是**直接执行工具、不再过门**,所以只要匹配上就不会循环、且会真正送达。本变更只需让匹配更鲁棒。

## 改动

1. 让 `_match_approval_command` 也能容忍**前导的纯文本 @token / bot 显示名**(例如剥掉任意 leading `@<非空白串>` 或 bot 自身 display name),再跑 `_APPROVAL_RE`。
2. 保留 id 格式校验(`[a-f0-9-]{6,36}`),确保散文如 `@bot approve the plan` 仍**不**误命中。
3. (可选)当文本"像审批命令但 id 不合法"时,回执更明确的提示,降低用户误用。

## 模块边界影响

- **owning package**:`im_gateway/`(`normalizer.py`)。
- **public API surface**:无签名变更,仅放宽匹配。
- **owned tables**:无。
- **config namespace**:无。
- **cross-module dependencies**:无新增。
- **migration / shim**:无。

## 分工

- **本地(你)**:改 `_strip_leading_mention`/`_match_approval_command` + 单测。
- **服务器(我)**:真实 Slack 验收(打字 approve 不再循环、消息送达)。

## 验收

DM 与频道下,`approve <id>`、`<@bot> approve <id>`、`@R. Alpha approve <id>` 三种写法都能正确 resolve 并送达,不再刷新 ID;`@bot approve the plan` 等散文不被误判为审批命令。
