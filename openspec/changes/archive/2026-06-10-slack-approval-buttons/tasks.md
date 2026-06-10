## 1. Block Kit 渲染助手 + send_to blocks 透传（outbound）

- [x] 1.1 Write failing tests for `approval_prompt_blocks`: 三按钮 action_id（approve/reject/approve_always）、value=approval_id、含 fallback 文本段；`send_to(..., blocks=...)` Slack DM/频道路径把 blocks 传给 chat_postMessage、Telegram 路径忽略
- [x] 1.2 Implement `approval_prompt_blocks` + `send_to`/`_slack_send_*` 可选 blocks 参数 to pass tests

## 2. gate 提示附带交互动作 + TypeError 降级（permission_gate）

- [x] 2.1 Write failing tests: requester 路由提示调用 `reply_func(text, blocks=...)`；reply_func 不接受 blocks（TypeError）时降级纯文本重发且流程不断；外呼通知 `send_to` 收到 blocks
- [x] 2.2 Implement prompt blocks attachment + degradation in `request_approval`/`_notify_approvers` to pass tests

## 3. Slack 点击处理（im_gateway/slack）

- [x] 3.1 Write failing tests for action handler: approve 点击 → `gate.resolve(id, "approved", 点击者id)` + `chat_update` 清按钮；approve_always 点击 → `always=True`；resolve 返回 False → `chat_postEphemeral` 且不 update；reply_func 接受 blocks kwarg
- [x] 3.2 Implement `app.action` 注册（`^approval_` 前缀单处理器）+ reply_func blocks 支持 to pass tests

## 4. 收尾

- [x] 4.1 更新 `docs/approval-and-outbound-decisions.md`（Change 2 决策 + Slack App 需开启 Interactivity 的部署要求）
- [x] 4.2 受影响层收尾：`make test-pr` 全绿；`uv run pytest tests/integration -q` 对照基线无新增失败
