# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。

## 1. 前置核实

- [x] 1.1 复读 `_append_delivery_trailer`(loop.py:299) + run finalize 调用(2244) + run_stream(2930)；`cron_scheduler._deliver` 静默检查(:224) + cron run 调用(:116)；确认 `_SILENT_SENTINEL`、receipt/`_r` 测试夹具

## 2. _append_delivery_trailer 增 emit 开关（TDD：红 → 绿）

- [x] 2.1 **测试先行**：`tests/unit/test_delivery_trailer.py` 加：构造 `SimpleNamespace(delivery_ledger=[_r("text",True)])`，断言 `loop._append_delivery_trailer("body", ctx, emit=False) == "body"`（无 📬）；`emit=True` → 含 📬；`emit=True` 空 reply → 仅 trailer。最窄命令 `uv run pytest tests/unit/test_delivery_trailer.py -x -q` **见红**（emit 参数不存在）
- [x] 2.2 **实现**：`_append_delivery_trailer(reply, tool_context, *, emit: bool = True)`，`emit=False` 直接返回 reply。**见绿**

## 3. _is_silent_reply 纯函数（TDD：红 → 绿）

- [x] 3.1 **测试先行**：新建 `tests/unit/test_cron_silent_delivery.py`，测 `cron_scheduler._is_silent_reply`：`[SILENT]`/`[SILENT]\n\n📬 实际投递…`/`  [SILENT]  `/`None`/`""`→True；`通知正文`/`[SILENT] 你好`→False。最窄命令 `uv run pytest tests/unit/test_cron_silent_delivery.py -x -q` **见红**（函数不存在）
- [x] 3.2 **实现**：`cron_scheduler` 加 `_is_silent_reply(reply)`（首个非空行 strip == sentinel / None / 空 → True）。**见绿**

## 4. 接线（wiring）

- [x] 4.1 `run()` 增 `emit_delivery_trailer: bool = True`，finalize 调用改 `_append_delivery_trailer(reply, tool_context, emit=emit_delivery_trailer)`
- [x] 4.2 `cron_scheduler` 触发 run 传 `emit_delivery_trailer=False`；`_deliver` 把静默检查改用 `_is_silent_reply(reply)`
- [x] 4.3 wiring 正确性由 task 5 全量回归保证；逻辑由 task 2/3 纯函数测试覆盖

## 5. 回归 + lint

- [x] 5.1 回归：`uv run pytest tests/unit/test_delivery_trailer.py tests/unit/test_cron_silent_delivery.py tests/unit/test_cron_typed_dispatch.py tests/unit/test_cron_fire_outbound_connectors.py tests/integration/test_cron_scheduler.py tests/integration/test_delivery_trailer_loop.py tests/unit/test_agent_loop.py -q` 全绿（含 IM 交互回执不回归）
- [x] 5.2 `uv run ruff check` + `ruff format --check` `src/fleetent/runtime/loop.py` `src/fleetent/cron_scheduler.py` + 测试 通过

## 6. spec 同步

- [x] 6.1 确认 `specs/scheduled-task-delivery/spec.md` 「SILENT reply suppresses delivery」MODIFIED 与实现一致（fired-run 不带操作者回执 trailer；静默判定对尾随内容鲁棒），含对应 scenario

## 7. 收尾验证

- [x] 7.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [x] 7.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [x] 7.3 回归确认（人读）：IM/Slack 交互投递回执（默认 emit=True）未变；run_stream(TUI) 未变；cron 投递目标解析未变；仅新增「cron run 不带 trailer + 静默判定鲁棒」
