## Why

定时任务给用户「莫名」发出一条 `[SILENT]\n\n📬 实际投递：消息 1（U09…UQ3）`。

实测(任务 `385f6080`,2026-06-22 09:14):任务=查金价→私信程鑫(U094B755UQ3),其最终回复**原样广播到频道 C092AUCV37V**;无需广播就回 `[SILENT]`。run 内 slack MCP 的 add_message 被禁,agent 改用内置 `send_im_message` 成功私信程鑫,模型最终正确回复 **`[SILENT]`**(不需要往频道广播)。

但 **agent loop finalize 的 `_append_delivery_trailer`**(run 里有 send_im_message 投递→台账非空)把 `\n\n📬 实际投递：消息 1（U09…UQ3）` 追加到回复后。于是 cron 拿到的 reply = `[SILENT]\n\n📬 实际投递…`,`cron_scheduler._deliver`(`:224`)判 `reply.strip() == "[SILENT]"` → **False**(被 trailer 污染)→ 未跳过 → 把整坨广播到频道,用户看到。

两层问题:
1. **trailer 污染了 `[SILENT]` 哨兵** → 该静默的 cron run 反而广播出去(本次的泄漏)。
2. **`📬 实际投递` 是面向操作者的回执**,而 cron 广播正文「不应包含面向操作者的说明」(任务提示词明令)——即便非静默的真实广播,带上回执也是噪声。

根因:`📬 实际投递` 回执是为**交互式对话**确认投递而设计的;**定时任务(无交互对象)的 run 不应追加它**。

## What Changes

- **cron 的 run 不追加投递回执**:`run()` 增加 `emit_delivery_trailer: bool = True`(默认不变,保持 IM/TUI 交互回执);`cron_scheduler` 触发 run 时传 `emit_delivery_trailer=False`。`_append_delivery_trailer` 增 `emit` 开关,`emit=False` 原样返回。
  - 效果:cron 回复回到干净的 `[SILENT]`(静默正确跳过)或干净的广播正文(无操作者回执)。
- **哨兵判定加固(纵深防御)**:`cron_scheduler` 增纯函数 `_is_silent_reply`,对尾随 trailer/空白鲁棒(首个非空行 == `[SILENT]` 即视为静默),`_deliver` 改用它。

不动:IM(Slack 交互)/ TUI 的投递回执(默认 `emit_delivery_trailer=True` 不变);`send_im_message` 本身;cron 投递目标解析。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `scheduled-task-delivery`：在「SILENT reply suppresses delivery」基础上明确——触发任务的 run 输出 MUST NOT 携带面向操作者的投递回执 trailer(它是交互式回执,定时任务无交互对象),使广播正文与 `[SILENT]` 哨兵保持干净;静默判定 MUST 对尾随 trailer/空白鲁棒(被回执等内容追加后仍能识别 `[SILENT]` 并跳过投递)。

## Impact

**owning package**：agent runtime —— `src/fleetent/runtime/loop.py`（`run` 增 `emit_delivery_trailer` 参数 + `_append_delivery_trailer` 增 `emit`）、`src/fleetent/cron_scheduler.py`（传 `emit_delivery_trailer=False` + `_is_silent_reply`）。不 import `fleetent.platform.*`。

**public API surface**：`run()` 新增可选参数 `emit_delivery_trailer: bool = True`（默认保持既有行为，调用方无需改动）；`_append_delivery_trailer` 新增 keyword-only `emit`（模块内私有）。`run_stream`（TUI）不变。

**owned tables**：无。

**config namespace**：无。

**cross-module dependencies**：cron_scheduler 已 import `runtime.loop`；无新增跨模块契约,不触碰 agent↔platform 边界。

**migration / shim plan**：无。

**受影响代码**：`runtime/loop.py`、`cron_scheduler.py`；测试 `tests/unit/test_delivery_trailer.py`(emit 开关)、`tests/unit/test_cron_silent_delivery.py`(`_is_silent_reply` 鲁棒性)。
