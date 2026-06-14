## 1. schedule_kind 校验（落库）

- [ ] 1.1 [test] `tests/integration/test_cron_scheduler.py`（或 schedule_store 测试）：`store.create`（或 `create_task`）传非法 `schedule_kind`（如 `"weekly"`）→ 抛 `ValueError` 含 `cron/once/interval`、且不落库。先见红。
- [ ] 1.2 [impl] `schedule_store.create` 校验 `schedule_kind ∈ {cron,once,interval}`（仿 task_type），非法抛 `ValueError`。见绿。

## 2. run_at → once 别名

- [ ] 2.1 [test] `create_task(schedule_kind="run_at", run_at="2026-…T…")` → 落库 `schedule_kind="once"`、`run_at` 归一为 canonical ISO、可正常注册（不抛、不落 cron 分支）。先见红。
- [ ] 2.2 [impl] `cron_scheduler.create_task` 在 run_at 归一化前加 `if schedule_kind == "run_at": schedule_kind = "once"`。见绿。

## 3. 工具文档

- [ ] 3.1 [docs] `schedule` 工具 docstring：明确 `schedule_kind` 仅 `cron`/`once`/`interval`；一次性任务用 `schedule_kind="once"` + `run_at`；勿把 `schedule_kind` 设为 `run_at`。

## 4. 收尾

- [ ] 4.1 [gate] `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
- [ ] 4.2 [gate] `uv run mypy src`（≤基线）+ 改动文件 `ruff check/format` 净。
