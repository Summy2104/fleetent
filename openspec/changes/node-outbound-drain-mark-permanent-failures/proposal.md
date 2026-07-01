# 变更:node outbound drain 对永久错误终态失败(消除无限重试)

母文档:`docs/records/aaa-8204-recovery.md`(node 健壮性,2026-06-30 真机验收发现)

> 本 proposal 由 agent 按用户内联 spec 起草,内容待人工确认。

## 为什么(实测证据)

`im_outbound_queue` drain(`node/im_edge.py` 的 `_deliver_queue_row`)对投递失败一律
`mark_failed_with_db`,而该函数实为「attempts+1 但 status 仍 `pending`」= 重试。永久错误
(`user_not_found` / `channel_not_found` / `not_in_channel` 等)永远不会因重试成功,于是队列项
永远 pending、每 interval(~10s)刷一次日志、永不消停(实测 `user_not_found` 每 10s 重试)。

## 改动

1. 新增终态 `outbound_queue_store.mark_dead_with_db`(`status='failed'`;`list_pending_with_db`
   只返回 `pending` → 不再被 drain 取到、不再重试)。
2. `_deliver_queue_row`:投递失败时经 `_is_permanent_delivery_error(receipt.error)` 分类——
   永久错误 → `mark_dead`(终态,记 warning);其余(网络/限流/未知)→ 保持 `mark_failed`(重试)。
3. 永久错误标记集(子串匹配 `receipt.error`):`user_not_found` / `users_not_found` /
   `channel_not_found` / `not_in_channel` / `is_archived` / `account_inactive` / `cannot_dm_bot`。

## 模块边界影响

- **owning package**:`node/`(`im_edge.py`,重试策略)+ `im_gateway/`(`outbound_queue_store.py`,新增终态方法)。
- **public API surface**:无破坏;新增 store 函数 + 内部分类器。
- **owned tables**:复用 `im_outbound_queue.status` 的 `'failed'` 终态值(无 schema 变更,`status` 为自由文本列)。
- **config / migration**:无。

## 分工

- **本地(你)**:分类器 + `mark_dead_with_db` + drain 路由 + 单测/集成测。
- **服务器(我)**:验收——永久错误不再每 10s 刷日志,队列项进入 `failed` 终态。

## 验收

永久错误的队列项一次失败即 `status='failed'`、不再被 drain 重试;瞬时错误仍 `pending` 重试(不回归)。
