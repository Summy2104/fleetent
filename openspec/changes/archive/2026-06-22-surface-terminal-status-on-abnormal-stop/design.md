# Design — surface-terminal-status-on-abnormal-stop

## 问题精确化

`run`(loop.py ~2086)与 `run_stream`(~2806)finalize:
```python
reply = (_msg_content if (msg and _msg_content) else ((msg.content if msg else None) or ""))
if stop_reason == StopReason.budget_exceeded:
    reply = await _grace_call(...)         # 仅 budget 有兜底
# reply 可能为 "" → run 返回空 / run_stream done 空
```
空 reply 经 `guard-empty-slack-reply` 守卫被跳过 → 静默。异常终止(loop_detected/consecutive_failures/approval_rejected/cancelled)无兜底。

tool 结果在 messages 里是 `{"role":"tool","tool_call_id":..,"content":<str>}`(loop.py:983/2786),最后一条 tool content 即「最后一步反馈/错误」。

## 决策

### D1. 用确定性文本兜底，不调 LLM
异常终止(尤其 loop_detected)时再发一次 LLM 调用有再次循环/再失败的风险,且慢。直接用 stop_reason → 固定中文模板 + 最后工具反馈拼接,稳定、零额外调用、可纯函数测试。

### D2. 三个纯函数,逻辑全部可隔离测
```python
def _last_tool_error(messages: list[Any]) -> str | None:
    """最后一条 role==tool 的 content（归一化、截断 200 字）；无则 None。"""

def _terminal_status_reply(stop_reason: StopReason, messages: list[Any]) -> str | None:
    """异常终止的用户可见状态文案；非异常（normal/budget_exceeded/awaiting_approval/
    mcp_strict_unavailable）返回 None（它们自有回复/兜底/早返回）。"""
    prefix = {
        StopReason.loop_detected: "我在重复调用同一个工具但没有进展，已停止以免空转。",
        StopReason.consecutive_failures: "连续多次工具调用失败，已停止。",
        StopReason.approval_rejected: "操作未获批准，已取消。",
        StopReason.cancelled: "任务已取消。",
    }.get(stop_reason)
    if prefix is None:
        return None
    if stop_reason in (StopReason.loop_detected, StopReason.consecutive_failures):
        err = _last_tool_error(messages)
        if err:
            return f"{prefix}最后一步的反馈：「{err}」。请换个方式或补充必要信息（如正确的参数 / ID）。"
    return prefix

def _finalize_reply(reply: str, stop_reason: StopReason, messages: list[Any]) -> str:
    """回复非空原样返回；异常终止且为空时替换为状态文案（否则仍返回原 reply）。"""
    if (reply or "").strip():
        return reply
    return _terminal_status_reply(stop_reason, messages) or reply
```

### D3. 两处 finalize 各一行接线
- `run`(在 budget grace 块之后、`_apply_output_transform` 之前):
  `reply = _finalize_reply(reply, stop_reason, messages)`
- `run_stream`(同位置)：因 reply 经 text_delta 流式发出,替换后需补发一条 delta：
  ```python
  _final = _finalize_reply(reply, stop_reason, messages)
  if _final != reply:
      reply = _final
      yield {"type": "text_delta", "content": reply}
  ```
  reply 非空时 `_final == reply`,不补发(零行为变化)。

放在 budget grace 之后:`budget_exceeded` 已被 grace 填好 reply,`_finalize_reply` 对它必返回原值(非空,或即便空 `_terminal_status_reply(budget_exceeded)` 也是 None → 不变)。

### D4. 不碰空回复守卫
`guard-empty-slack-reply` 保持原样;本 change 让异常终止产出**非空** reply,守卫自然放行投递。两者正交。

## 测试策略（unit，纯函数）

新增 `tests/unit/test_loop_terminal_status.py`:
- `_last_tool_error`:取最后一条 tool content（多条取最后）；归一化空白 + 截断；无 tool → None；非 dict/无 content → 跳过。
- `_terminal_status_reply`:loop_detected + tool err → 含 prefix + err + 「请换个方式」；consecutive_failures 同；loop_detected 无 tool → 仅 prefix；approval_rejected/cancelled → 各自文案（不含 err）；normal/budget_exceeded/awaiting_approval/mcp_strict_unavailable → None。
- `_finalize_reply`:非空 reply 原样；空 + loop_detected → 状态文案；空 + normal → 原空串（无兜底）；空白串 "  " 视为空。

wiring（两处 finalize 调 `_finalize_reply`）由**全量 loop/run 回归**保证不破坏既有行为(空回复守卫、正常完成、budget grace、审批挂起测试均不回归);逻辑正确性由上述纯函数测试覆盖。

## 可观测信号
异常终止后,run 返回 / run_stream done 带非空状态文案 → Slack 收到「停了 + 原因 + 最后错误」而非沉默；正常/预算/审批路径回复不变。
