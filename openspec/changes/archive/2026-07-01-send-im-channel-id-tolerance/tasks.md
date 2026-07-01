# Tasks:send-im-channel-id-tolerance(问题 ⑦)

标记:`[本地]` 纯代码+单测;`[服务器]` 真机验收。

## 实现(TDD,test 先于 impl)
- [x] [本地] 写测试:`send_to` slack,`target=D…`/`C…`(`target_type=user`)→ 直接 `chat_postMessage(channel=target)`、不调 `conversations_open`(见红)。
- [x] [本地] 实现:`_slack_is_channel_id` 判定 `C`/`D`/`G` 开头;`_slack_send_dm`/`_slack_send_file` 对 channel 形 id 直发(见绿)。
- [x] [本地] 写测试(回归):`target=U…` 仍 `conversations_open` 开 DM 再 post(既有 `test_send_to_slack_opens_dm_then_posts`)。
- [x] [本地] 收紧 `send_im_message` docstring(`target_type=user` → `target` 必须 `U…`,非 DMChannelID)。

## 收尾
- [x] [本地] `make test-pr` + `make test-integration-ci` 全绿。
- [x] [服务器] 真机验收:批准后程鑫**真的收到**,无 `user_not_found` 重试。
