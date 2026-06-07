## 1. 结构化摘要模板（TDD）

- [x] 1.1 写失败测试（`tests/unit`）：`_build_summary_prompt` 首次分支与增量分支（有 `prev_summary`）均含固定分节标记（如 `## Next Steps`、`In Progress`）+ 逐字保留未完成工作/下一步的指令；增量分支要求"并入既有分节"。运行 `uv run pytest tests/unit -x -q` 看红
- [x] 1.2 实现：重写 `_build_summary_prompt` 为结构化模板（两分支同结构）。看绿

## 2. active-task 续跑块（TDD）

- [x] 2.1 写失败测试（`tests/unit`，`monkeypatch SESSIONS_DIR` + 写 `.todo`，`patch` `_summarize` 返回固定串避免真实 LLM）：有未完成 todo 时 `_compress` 结果在 head 后、summary 前含 `_ACTIVE_TASK_PREFIX` 的 system 块且逐字列出未完成项；全 completed / 空 / 无 session_id / 读 `.todo` 失败时不注入；active 块 token 计入投影（尾部不显著超 target）；不破坏 head/tail identity 去重。看红
- [x] 2.2 实现：新增 `_active_task_block(session_id)` + `_ACTIVE_TASK_PREFIX`；`_compress` 在 summarized/degraded 路径注入（no_middle 不注入）；`_select_tail` 增加 `extra_fixed` 计入 active 块 token。看绿

## 3. 收尾

- [x] 3.1 `uv run ruff format`（仅改动文件）、`uv run ruff check`（改动文件）、`uv run mypy src/fleetent/runtime/context.py`、全量 `uv run pytest -x -q`
- [x] 3.2 `openspec validate compression-continuation-summary --strict` 通过
