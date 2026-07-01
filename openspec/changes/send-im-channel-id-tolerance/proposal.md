# 变更:send_im_message 容忍 channel 形 target(批准后真正送达)

母文档:`docs/records/aaa-8204-recovery.md`(问题 ⑦,2026-06-30 真机验收发现 —— 当前最后一个「送达」拦路）

> 本 proposal 由 agent 按用户内联 spec 起草,内容待人工确认。

## 为什么(实测证据)

`approve 721dd5f0` 后 `im_outbound_queue` 成功入队(⑥ 生效),但 node drain 投递报
`slack_send_dm_failed error='user_not_found' user_id=D0B4VQKHFEU`(每 10s 重试)。

根因:`users_search` 返回 `UserID=U094B755UQ3` + `DMChannelID=D0B4VQKHFEU`,agent 把
`DMChannelID`(`D` 开头的频道 id)当成 user 填进了 `target`(`target_type=user`)→ Slack
`conversations.open(users=[D…])` → `user_not_found`。

## 改动

1. **连接器容错**:`_slack_send_dm` / `_slack_send_file` 当 `target` 形如频道 id(`C…`/`D…`/`G…` 开头)时,
   **无论 `target_type`**,直接 `chat_postMessage(channel=target)`,不走 `conversations.open(user=…)`。
   这样 agent 误填 `DMChannelID` 也能送达。
2. **收紧 docstring**:`send_im_message` 的 `target_type=user` 时 `target` 必须是用户 id(`U…`),
   不是 `DMChannelID`。

## 模块边界影响

- **owning package**:`fleetent.outbound`(顶层投递原语)+ `tools/`(`send_im_message` docstring)。
- **public API surface**:无签名变更,仅放宽 slack 投递目标解析 + docstring 收紧。
- **owned tables / config / migration**:无。
- **cross-module dependencies**:无新增。

## 分工

- **本地(你)**:连接器 channel-id 容错 + docstring + 单测。
- **服务器(我)**:真机验收——批准后程鑫**真的收到**。

## 验收

`target` 为 `D…`/`C…` 时按 channel 直接投递成功;`target=U…` 仍走 user DM(开 DM 再 post);
不再 `user_not_found` 无限重试。
