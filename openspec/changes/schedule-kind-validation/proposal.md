## Why

模型创建一次性定时任务时常把参数名 `run_at` 误当成 `schedule_kind` 的值（传 `schedule_kind="run_at"`，本应 `schedule_kind="once"` + `run_at=<时间>`）。系统**不校验 `schedule_kind`**（仅校验 `task_type`），非法值被静默落库；注册时 `run_at` 既非 `once` 也非 `interval` → 落到 cron 分支 → `CronTrigger.from_crontab(None)` → `'NoneType' object has no attribute 'split'` → 注册失败。`cron-runat-hardening` 的启动韧性把崩溃兜住了（不崩 boot、自动 disable），但代价是**任务从不触发**——实测：用户"一分钟后提醒我喝水"，agent 重试 5 次全失败、提醒从未到来。

## What Changes

- **`run_at` 作为 `once` 的别名**：`create_task` 在归一化前把 `schedule_kind="run_at"` 视为 `"once"`（这是模型把参数名当 kind 的高频混淆，意图明确——一次性任务），使此类请求**直接成功**而非失败重试。
- **`schedule_kind` 落库校验**：`schedule_store.create` 校验 `schedule_kind ∈ {cron, once, interval}`（仿 `task_type` 校验），非法值 MUST 抛 `ValueError` 并附清晰信息（如 `invalid schedule_kind 'xxx' (cron/once/interval)`），由 `schedule` 工具转为干净错误文本让 agent 自纠，而非静默落库后注册崩。
- **工具文档强化**：`schedule` 工具 docstring 明确 `schedule_kind` 只能是 `cron`/`once`/`interval`，一次性任务用 `schedule_kind="once"` 并把时间放 `run_at`，**不要把 `schedule_kind` 设成 `run_at`**。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `cron-scheduled-tasks`: 「Schedule kinds cron, one-shot, and interval」新增 `schedule_kind` 校验（非法即拒）+ `run_at`→`once` 别名归一化的要求。

## Impact

- **owning package**：top-level `cron_scheduler.py`（`create_task` 别名归一）、`schedule_store.py`（`create` 校验）、`tools/builtin_tools.py`（`schedule` docstring）。
- **public API surface**：`schedule_store.create` 对非法 `schedule_kind` 由"静默接受"改为"抛 ValueError"（行为收紧；合法值不变）。`create_task` 接受 `"run_at"` 并归一为 `"once"`。
- **owned tables**：无（`scheduled_tasks` schema 不变）。
- **config namespace**：无。
- **cross-module dependencies**：无新增；不碰 agent⊥platform。
- **migration / shim plan**：无 schema 迁移。存量 `schedule_kind="run_at"` 的坏行不会被回改（它们已被启动韧性 disable）；新建走别名+校验路径。
- **不在范围**：把 LLM 工具 schema 的 `schedule_kind` 渲染成 enum（需增强 registry schema builder 支持 `Literal`→enum，跨切面，另行评估）。本次靠别名+校验+文档解决。
