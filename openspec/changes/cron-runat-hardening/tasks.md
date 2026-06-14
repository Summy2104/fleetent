## 1. run_at 解析鲁棒性

- [ ] 1.1 [test] `tests/unit/test_cron_scheduler.py`（或新增）：`_parse_run_at` 容忍 `"2026-06-14 08:07:19 UTC"`、`"…Z"`、空格分隔；仍支持严格 ISO + 相对 `+30m`；无法解析抛 ValueError。先见红。
- [ ] 1.2 [impl] `cron_scheduler._parse_run_at` 归一化（` UTC`/` GMT`→`+00:00`、`Z` 接受）后再 `fromisoformat`。见绿。

## 2. 启动韧性（核心）

- [ ] 2.1 [test] `start()`：store 含一条坏 `run_at` 的 `once` 任务 + 若干正常任务 → 坏任务被记 warning + `set_enabled(False)` + 跳过，正常任务全部注册，`scheduler.start()` 正常、boot 不抛。先见红。
- [ ] 2.2 [impl] `start()` 的注册循环每任务舱壁化（try/except → warning + `_store.set_enabled(id, False)` + continue）。见绿。

## 3. 写入端规范化

- [ ] 3.1 [test] `schedule` 工具创建 `once`：`run_at="…UTC"` → 落库为 canonical ISO（带 `+00:00`）；不可解析 `run_at` → 返回错误文本且不落库。先见红。
- [ ] 3.2 [impl] `schedule` 工具创建 `once` 时经 `_parse_run_at` 规范化后存 `parsed.isoformat()`；解析失败返回明确错误、不调用 store.create。见绿。

## 4. 收尾

- [ ] 4.1 [gate] `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
- [ ] 4.2 [gate] `uv run mypy src`（≤基线）+ 改动文件 `ruff check/format` 净。
