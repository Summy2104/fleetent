# Tasks:node-outbound-drain-mark-permanent-failures(node 健壮性)

标记:`[本地]` 纯代码+单测/集成测;`[服务器]` 真机验收。

## 实现(TDD,test 先于 impl)
- [x] [本地] 写测试:`_is_permanent_delivery_error` 对 `user_not_found`/`channel_not_found`/`not_in_channel`/`is_archived` 为真;对 `boom`/`ratelimited`/空 为假(见红)。
- [x] [本地] 实现:`_is_permanent_delivery_error` 分类器 + `outbound_queue_store.mark_dead_with_db`(`status='failed'`);`_deliver_queue_row` 按分类路由(见绿)。
- [x] [本地] 写测试(集成):永久错误 drain 后 `status='failed'`、二次 drain 不再 `send_to`(见红→绿)。
- [x] [本地] 写测试(回归):瞬时错误(`boom`)仍 `status='pending'`、`attempts+1`(既有 `test_node_im_edge_failed_send_increments_attempts_and_leaves_pending` 保留)。

## 收尾
- [x] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [ ] [服务器] 验收:永久错误不再每 10s 刷日志,队列项进入 `failed` 终态。
