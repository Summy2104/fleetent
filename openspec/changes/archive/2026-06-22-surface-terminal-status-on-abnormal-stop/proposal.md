## Why

run 因**异常终止**(anti-flap 循环检测 / 连续失败 / 取消 / 审批拒绝)结束、且最后一条 assistant 文本为空时,用户在 Slack 收到的是**沉默**——什么反馈都没有。

实测(2026-06-22 ~07:22,session `…1782099741…`):bot 反复调 armada 查用户工具,每次返回「需要 slackUserId 来定位用户」,触发重复检测护栏(`StopReason.loop_detected`)终止;此时 `reply` 为空串,经空回复守卫(`guard-empty-slack-reply`)跳过投递 → 用户完全不知道发生了什么、卡在哪。

根因在 `runtime/loop.py` 两处 finalize(`run` ~2086 / `run_stream` ~2806):

```python
reply = (_msg_content if (msg and _msg_content) else ((msg.content if msg else None) or ""))
if stop_reason == StopReason.budget_exceeded:
    reply = await _grace_call(...)   # ← 只有「预算耗尽」有兜底总结
```

只有 `budget_exceeded` 有 Grace Call 兜底;`loop_detected` / `consecutive_failures` / `approval_rejected` / `cancelled` 都没有,`reply` 留空 → 沉默。

## What Changes

- 新增确定性兜底:run 以**异常原因终止**且 `reply` 去空白后为空时,合成一条**用户可见的状态回复**,说明「停了 + 为什么 + 最后一步的错误/工具反馈」,而非沉默。
  - `loop_detected`:说明在重复调用同一工具未取得进展、已停止,并附**最后一条工具反馈**(如「需要 slackUserId 来定位用户」),提示换方式/补参数。
  - `consecutive_failures`:说明连续工具失败、已停止 + 最后错误。
  - `approval_rejected`:说明操作未获批准、已取消。
  - `cancelled`:说明任务已取消。
- 用**确定性文本**合成(不再调 LLM——异常终止时再调 LLM 可能又循环);`budget_exceeded`(已有 grace)/ `awaiting_approval`(已发审批 prompt)/ `normal` 不受影响。
- 两条路径都修:`run`(IM/Slack,返回 reply)与 `run_stream`(TUI,补发一条 `text_delta`)。

不动:正常完成、budget grace、审批挂起、空回复守卫本身(本 change 让「异常终止」产出非空回复,守卫自然就会投递)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-loop-termination`:新增要求——异常原因终止(loop_detected / consecutive_failures / approval_rejected / cancelled)且已有回复为空时,主循环 SHALL 返回一条用户可见的状态回复(含原因 + 适用时附最后一条工具反馈/错误),MUST NOT 返回空回复导致静默。既有「返回当前已有回复」语义在回复非空时不变。

## Impact

**owning package**:agent runtime —— `src/fleetent/runtime/loop.py`(两处 finalize + 新增纯函数助手)。不 import `fleetent.platform.*`。

**public API surface**:无对外 API 变化(新增模块级私有 `_last_tool_error` / `_terminal_status_reply` / `_finalize_reply`;`run` / `run_stream` 签名与返回类型不变)。

**owned tables**:无。

**config namespace**:无。

**cross-module dependencies**:仅用既有 `StopReason`(runtime.termination)与 messages 列表;不新增依赖,不触碰 agent↔platform 边界。

**migration / shim plan**:无。

**受影响代码**:`runtime/loop.py`(`_last_tool_error` / `_terminal_status_reply` / `_finalize_reply` + `run`/`run_stream` finalize 各一处接线);测试 `tests/unit/test_loop_terminal_status.py`(纯函数全分支)。
