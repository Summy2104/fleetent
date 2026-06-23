# Design — fix-cron-reply-trailer-leak

## 问题精确化

`_append_delivery_trailer(reply, tool_context)`(loop.py:299)在台账(`tool_context.delivery_ledger`)非空时把 `\n\n📬 实际投递：…` 追加到 reply,run() 在 finalize 调用(2244)。cron 经 `agent_loop.run(...)`(cron_scheduler:116)触发 run,run 内的 `send_im_message` 把投递记进台账 → trailer 被追加。

cron `_deliver`(cron_scheduler:224)：`reply.strip() == _SILENT_SENTINEL` 才跳过。`[SILENT]\n\n📬…` ≠ `[SILENT]` → 不跳过 → 把整坨(含哨兵+回执)广播。

## 决策

### D1. 定时任务的 run 不追加交互式回执（根因修复）
`📬 实际投递` 是交互式对话里给用户确认投递用的;定时任务无交互对象、其回复是广播正文。故 cron run **不应**追加它。

- `_append_delivery_trailer` 增 keyword-only `emit: bool = True`：`emit=False` 直接返回原 reply(不渲染、不追加)。
- `run()` 增 `emit_delivery_trailer: bool = True`,finalize 调用改为 `_append_delivery_trailer(reply, tool_context, emit=emit_delivery_trailer)`。默认 True → IM/Slack 交互回执不变。
- `cron_scheduler` 触发 run 时传 `emit_delivery_trailer=False`。
- `run_stream`(TUI 交互)不变(默认仍追加)。

效果:cron 回复 = 干净的 `[SILENT]`(→ 正确跳过)或干净广播正文(无操作者回执噪声)。

### D2. 哨兵判定加固（纵深防御）
即便将来有别的尾随内容,cron 静默判定也不该被破坏。新增纯函数：
```python
def _is_silent_reply(reply: str | None) -> bool:
    """fired-task reply 是否为静默哨兵（对尾随 trailer/空白鲁棒）。
    None 视为静默（无内容可发）；首个非空行 strip 后 == [SILENT] 即静默。"""
    if reply is None:
        return True
    stripped = reply.strip()
    if not stripped:
        return True
    return stripped.splitlines()[0].strip() == _SILENT_SENTINEL
```
`_deliver` 把 `reply is None or reply.strip() == _SILENT_SENTINEL` 换成 `if _is_silent_reply(reply): return None`。

注:模型把 `[SILENT]` 作为整条回复(首行),任何 trailer 追加在后续行 → 首行判定稳。`[SILENT] 额外正文`(同一行有正文)→ 首行 != `[SILENT]` → 不静默(正确:模型确实想发东西)。

### D3. 两个修复正交、互补
- D1 去掉污染源(也清理广播噪声)。
- D2 即便污染源以后又出现(别的 trailer/transform 追加),静默仍可靠。
- 二者都做:止血 + 韧性。

## 测试策略（unit，纯函数）

1. `test_delivery_trailer.py` 补 `_append_delivery_trailer` 的 emit 开关：
   - 构造带成功 receipt 的 fake tool_context（`SimpleNamespace(delivery_ledger=[_r("text",True)])`,复用现有 `_r`）。
   - `emit=False` → 返回原 reply（无 📬）；`emit=True`（默认）→ 含 📬；空 reply + emit=True → 仅 trailer（既有行为不回归）。
2. 新建 `test_cron_silent_delivery.py` 测 `_is_silent_reply`：
   - `[SILENT]`→True；`[SILENT]\n\n📬 实际投递：消息 1（U0…）`→True；`  [SILENT]  `→True；`None`→True；`""`→True；`通知正文`→False；`[SILENT] 你好`(同行)→False。

wiring（run 传参、cron 传 `emit_delivery_trailer=False`、`_deliver` 用 `_is_silent_reply`）由全量 cron/trailer/loop 回归保证不破坏既有行为。

## 可观测信号
定时任务静默时不再向频道泄漏 `[SILENT] + 回执`；真实 cron 广播为干净正文(无 `📬 实际投递`);IM/TUI 交互回执不变。
