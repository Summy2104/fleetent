## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `eval_logger.py` 的 `_LOG_PATH`（行 12）与既有 append 写法（`mkdir` + `json.dumps(ensure_ascii=False)`）、可选字段 `if x is not None` 模式（log_run 行 50-61），据此新增 `log_sandbox_exec`
- [ ] 1.2 核实 `run_code`（tools.py 行 49-69）执行路径：`ExecResult` 已含 stdout/stderr/exit_code，确认耗时与字节大小可在现路径廉价算出，无需改 `SandboxClient`
- [ ] 1.3 确认 `sandbox_scope` 在 SB2 未落地前传 `None`，字段可选不写入；SB2 落地后接 `Scope` 字符串

## 2. 沙箱执行 trace 出口（eval_logger.py）

- [ ] 2.1 Write failing tests：`log_sandbox_exec(elapsed_s, exit_code, stdout_bytes, stderr_bytes)` append 一条 JSONL，含 `kind="sandbox_exec"`、`ts`、`elapsed_s`（保留 3 位）、`exit_code`、`stdout_bytes`、`stderr_bytes`；可选字段（sandbox_scope/agent_name/user_id）为 None 时不出现在记录中，非 None 时出现。`monkeypatch _LOG_PATH` 到 tmp_path。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `log_sandbox_exec`（复用 `_LOG_PATH` append 写法 + 可选字段 `if not None` 模式），看到绿
- [ ] 2.3 Write failing test：`log_sandbox_exec` 不记录代码原文或完整 stdout/stderr 内容，仅记字节大小（断言记录中无原文字段）。看到红
- [ ] 2.4 Implement 确保仅写元数据，看到绿

## 3. run_code 接入 trace（tools.py）

- [ ] 3.1 Write failing tests：`run_code` 执行后调用 `log_sandbox_exec`，传入正确的 `exit_code`、`stdout_bytes=len(stdout.encode())`、`stderr_bytes=len(stderr.encode())` 与正向 `elapsed_s`；返回文本格式不变。mock SandboxClient/Manager + `time.monotonic`，断言 `log_sandbox_exec` 调用参数。看到红
- [ ] 3.2 Implement：`run_code` 用 `time.monotonic` 测 exec 时长、算字节大小、调用 `log_sandbox_exec`，看到绿

## 4. trace 失败不阻断执行

- [ ] 4.1 Write failing test：`log_sandbox_exec` 抛异常时 `run_code` 仍正常返回代码执行结果，并记录一条警告（mock `log_sandbox_exec` 抛异常，断言返回值正常 + warning）。看到红
- [ ] 4.2 Implement：`run_code` 内 trace 写入包 try/except，失败 `logger.warning` 不 re-raise，看到绿

## 5. 收尾

- [ ] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 5.3 `uv run mypy src` 无新增错误
