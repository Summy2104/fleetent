# Design — guard-empty-slack-reply

## 问题精确化（实测取证）

traceback 链:`handle_mention → _handle → route → reply_func(response)`(`normalizer.py:725`)→ `_make_status_funcs` 的 `reply_func` 在 `slack.py:141` `await say(**{"text": "", "thread_ts": ...})` → Slack `chat.postMessage` 返回 `{'ok': False, 'error': 'no_text'}` → `SlackApiError` 冒泡到 bolt listener（`Failed to run listener function`）。

空文本来自 agent 的空回合（仅工具调用 / 审批挂起占位 → 最终 reply 文本为空）。Slack 不接受空 `text` 且无 `blocks` 的消息。

三处回复路径都可能踩到:
1. `_make_status_funcs.reply_func`(~131-141):`say(**{"text": text, "thread_ts": ...[, "blocks"]})`。
2. 审批动作 resume `_reply`(~228-232):`client.chat_postMessage(**{"channel": ..., "text": text[, "blocks"]})`。
3. mention `reply_func`(~434-440):`say(text=text, blocks=blocks)` / `say(text)`。

## 决策

### D1. 统一判定 helper，三处投递前短路
```python
def _has_postable_content(text: str, blocks: list[dict[str, Any]] | None) -> bool:
    """Slack rejects chat.postMessage with empty text and no blocks (no_text); a reply
    with neither is skipped rather than raising."""
    return bool((text or "").strip()) or bool(blocks)
```
- 文本去空白后非空 **或** 有 blocks → 可投递（保留 blocks-only 合法消息）。
- 纯空白文本（`""`/`"  "`/`"\n"`）且无 blocks → 跳过。

### D2. 守卫位置：状态清除之后、Slack 调用之前
每处先做既有的状态指示清除（`assistant_threads_setStatus("")` / `set_status("")`，best-effort），**再**判 `_has_postable_content`，不满足则 `return`（path 1 改 `if say is not None and _has_postable_content(...)`）。保证「思考中」指示器照常消失，仅省掉空投递。

### D3. 不改 normalizer 调用方
`normalizer.py:725` 仍无条件 `await msg.reply_func(response)`；守卫放在 **Slack 适配器侧**(平台特定:Slack 拒空消息;别的平台策略可不同),覆盖全部三处调用方,单一边界。

## 测试策略（unit，扩 test_slack_assistant.py）

1. **helper 纯函数**:`_has_postable_content("", None) is False`；`("  ", None) False`；`("hi", None) True`；`("", [{"type":"section"}]) True`。
2. **`_make_status_funcs` reply_func 守卫**:`reply_func("")` → `say` **未** await；`reply_func("hi")` → `say` 被 await（text="hi"）；`reply_func("", blocks=[...])` → `say` 被 await。用 fake client(`assistant_threads_setStatus` AsyncMock) + `say=AsyncMock()` 直接构造。
3. 既有 `test_assistant_reply_clears_status_and_says`（非空 "final answer"）必须仍绿（回归）。

均 AsyncMock，无真实 Slack/网络,合 unit 边界。

## 可观测信号
修复后:空回合不再触发 `chat.postMessage` 调用,journal 不再出现 `no_text` SlackApiError / `Failed to run listener function`;审批 prompt / 非空回复正常投递,不再因空回复异常中断 listener。
