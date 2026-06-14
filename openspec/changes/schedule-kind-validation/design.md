## Context

`schedule` 工具 → `cron_scheduler.create_task`（模块函数，choke point）→ `schedule_store.create`（落库）/ 运行中则经 `CronScheduler.create_task` 方法。`store.create` 校验 `task_type ∈ {notify,generate,action}`，但 **不校验 `schedule_kind`**（`str` 默认 `"cron"`）。`create_task` 仅在 `schedule_kind == "once"` 时归一 `run_at`（cron-runat-hardening）。注册 `_register`：`kind = schedule_kind or "cron"`，`once`/`interval` 各有分支，**其余（含 `"run_at"`）落 cron 分支** → `CronTrigger.from_crontab(cron_expr=None)` → `'NoneType'.split'` 崩（被启动韧性兜住、disable，任务不触发）。

registry 的工具 schema builder 不支持 `Literal`→enum，故无法仅靠类型注解约束 LLM 输入；防线放在创建路径。

## Goals / Non-Goals

**Goals:**
- 模型把 `schedule_kind` 误设为 `"run_at"` 的高频情况**直接成功**（别名→`once`）。
- 非法 `schedule_kind` 在创建时**清晰报错**，不再静默落库后注册崩。
- 文档引导模型用对 kind。

**Non-Goals:**
- 不增强 registry schema builder 支持 `Literal`→enum（跨切面，另议）。
- 不回改存量坏行（已被韧性 disable）。
- 不改 `_register` 的 kind 分支结构（校验前移后，非法 kind 到不了注册）。

## Decisions

### D1：`run_at`→`once` 别名（create_task 顶部）
`cron_scheduler.create_task` 在现有 `run_at` 归一化**之前**加：`if schedule_kind == "run_at": schedule_kind = "once"`。这样 `kind` 先归一，随后 `if schedule_kind == "once" and run_at` 的 ISO 归一也能命中。
- **为何别名而非直接拒**：这是"参数名当 kind 值"的明确意图（一次性任务），别名让用户请求**一次成功**，避免 agent 重试/放弃（实测它会连试 5 次然后摆烂）。其余非法 kind 才靠 D2 拒。
- **为何在 create_task 而非 store.create**：create_task 是 run_at 归一的同一 choke point，别名在此与既有归一相邻、顺序正确；store.create 仍做最终校验兜底。

### D2：`schedule_kind` 落库校验（store.create）
`schedule_store.create` 仿 `task_type`：`if schedule_kind not in ("cron","once","interval"): raise ValueError(f"invalid schedule_kind: {schedule_kind!r} (cron/once/interval)")`。`schedule` 工具已 `except ValueError` 转干净文本，故 agent 收到明确错误可自纠。
- 经 create_task 的别名后，`"run_at"` 已变 `"once"`、通过校验；直接调 store.create 传非法 kind → 拒。

### D3：工具 docstring 强化
`schedule` 工具 create 段明确：`schedule_kind` 仅 `cron`/`once`/`interval`；一次性任务用 `schedule_kind="once"` + `run_at`；**勿把 `schedule_kind` 设为 `run_at`**。降低模型再犯概率。

## Risks / Trade-offs

- [别名掩盖模型错误] → 别名只覆盖 `run_at`→`once` 这一意图明确的高频混淆；其余非法 kind 仍按 D2 显式拒，错误可见。
- [store.create 收紧为抛错可能影响误传非法 kind 的既有调用方] → 生产唯一调用方是 schedule 工具（经 create_task 别名 + 已 catch ValueError）；cron/once/interval 合法值行为不变。
- [未约束 LLM schema] → 别名 + 校验 + 文档三管;真要根治模型乱传需 schema builder 支 enum（Non-Goal，记档）。
