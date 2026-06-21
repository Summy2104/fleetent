## Why

端到端实测(2026-06-21)日志里反复出现 traceback:

```
slack.py:141 reply_func → say(**kwargs) → chat.postMessage
slack_sdk.errors.SlackApiError: ... {'ok': False, 'error': 'no_text'}
Failed to run listener function (error: ... 'no_text')
```

根因:agent 某些回合产出**空文本**(只调工具、或审批挂起占位等),`normalizer.py:725 await msg.reply_func(response)` 把空串传进 Slack 回复函数,`chat.postMessage` 以空 `text` 且无 `blocks` 被 Slack 拒(`no_text`),异常冒泡到 bolt listener。后果:listener 报错、回复/审批 prompt 投递中断,实测中还伴随重复审批。Slack 本就不接受空消息,空回复**应当跳过**而非报错。

slack.py 有三处回复路径都可能用空文本调 Slack:`_make_status_funcs` 的 `reply_func`(assistant/mention,~141)、审批动作 resume 的 `_reply`(~228)、mention handler 的 `reply_func`(~434)。

## What Changes

- 新增模块级判定 `_has_postable_content(text, blocks)`:文本去空白后非空 **或** 存在 blocks 才可投递。
- 三处回复路径在调用 `say` / `chat_postMessage` 前用它兜底:无可投递内容时**直接跳过**(状态指示器照常清除),不调用 Slack API、不抛 `no_text`。

不动:线程优先、状态指示、blocks-only 消息(有 blocks 即可投递)、非空回复行为。仅在投递前加空内容短路。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `im-gateway`:新增要求——回复投递在文本为空(去空白后)且无 blocks 时 SHALL 跳过,MUST NOT 以空文本调用 Slack `chat.postMessage`(避免 `no_text` 报错中断 listener);有 blocks 的空文本消息仍可投递。

## Impact

**owning package**:agent runtime —— `src/fleetent/im_gateway/slack.py`（三处回复路径 + 一个判定 helper）。不 import `fleetent.platform.*`。

**public API surface**:无对外 API 变化（新增模块级私有 `_has_postable_content`；reply_func 签名不变）。

**owned tables**：无。

**config namespace**：无。

**cross-module dependencies**：无新增；不触碰 agent↔platform 边界。

**migration / shim plan**：无。

**受影响代码**：`im_gateway/slack.py`（`_has_postable_content` + `_make_status_funcs`/审批 `_reply`/mention `reply_func` 三处守卫）；测试 `tests/unit/test_slack_assistant.py`（空文本不投递 / 非空投递 / blocks-only 投递）。
