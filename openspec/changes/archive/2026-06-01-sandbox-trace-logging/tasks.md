## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `eval_logger.py` 的两个路径常量 `_LOG_PATH`（行 12，`log_run` 用）与 `TRACE_PATH`（行 13，`log` 用）取值相同（都是 `data/traces.jsonl`）、既有 append 写法（`mkdir` + `json.dumps(ensure_ascii=False)`）、可选字段 `if x is not None` 模式（log_run 行 51-64），据此合并常量并新增 `log_sandbox_exec`
- [x] 1.2 核实 `log_run`/`log` 既有记录**均无 `kind` 字段**、且 traces.jsonl **当前无任何消费者**（只写不读），确认追加 `kind` 为纯增量、零风险
- [x] 1.3 核实 `run_code`（tools.py 行 49-69）执行路径：`ExecResult` 已含 stdout/stderr/exit_code，确认耗时与字节大小可在现路径廉价算出，无需改 `SandboxClient`
- [x] 1.4 确认 `sandbox_scope` 在 SB2 未落地前传 `None`，字段可选不写入；SB2 落地后接 `Scope` 字符串

## 2. 合并重复路径常量（eval_logger.py）

- [x] 2.1 Write failing test：monkeypatch 单一 trace 路径常量到 tmp_path 后，`log_run` 与 `log` 两者的写入都落到该 tmp_path（断言 `TRACE_PATH` 别名已不存在或与统一常量同一对象），证明不再有「漏隔离」的第二常量。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：把 `_LOG_PATH` 与 `TRACE_PATH` 合并为单一常量，`log_run`/`log` 均引用它，看到绿

## 3. 统一 trace taxonomy——给 log_run/log 补 kind（eval_logger.py）

- [x] 3.1 Write failing tests：`log_run` 写入的记录含 `kind: "agent_run"`、`log` 写入的记录含 `kind: "im_message"`；**既有 trace 调用向后兼容**——断言 `log_run`/`log` 原有字段（input/reply/messages/tokens/elapsed_s、user_id/platform 等）取值与结构一概不变，仅多出 `kind` 一个键。看到红
- [x] 3.2 Implement：在 `log_run`/`log` 的 entry 中追加 `kind` 字段（不动任何既有字段），看到绿

## 4. 沙箱执行 trace 出口（eval_logger.py）

- [x] 4.1 Write failing tests：`log_sandbox_exec(elapsed_s, exit_code, stdout_bytes, stderr_bytes)` append 一条 JSONL，含 `kind="sandbox_exec"`、`ts`、`elapsed_s`（保留 3 位）、`exit_code`、`stdout_bytes`、`stderr_bytes`；可选字段（sandbox_scope/agent_name/user_id）为 None 时不出现在记录中，非 None 时出现。monkeypatch 统一 trace 路径常量到 tmp_path。运行 `uv run pytest -x -q` 看到红
- [x] 4.2 Implement `log_sandbox_exec`（复用统一常量 append 写法 + 可选字段 `if not None` 模式），看到绿
- [x] 4.3 Write failing test：`log_sandbox_exec` 不记录代码原文或完整 stdout/stderr 内容，仅记字节大小（断言记录中无原文字段）。看到红
- [x] 4.4 Implement 确保仅写元数据，看到绿

## 5. run_code 接入 trace（tools.py）

- [x] 5.1 Write failing tests：`run_code` 执行后调用 `log_sandbox_exec`，传入正确的 `exit_code`、`stdout_bytes=len(stdout.encode())`、`stderr_bytes=len(stderr.encode())` 与正向 `elapsed_s`；返回文本格式不变。mock SandboxClient/Manager + `time.monotonic`，断言 `log_sandbox_exec` 调用参数。看到红
- [x] 5.2 Implement：`run_code` 用 `time.monotonic` 测 exec 时长、算字节大小、调用 `log_sandbox_exec`，看到绿

## 6. trace 失败不阻断执行

- [x] 6.1 Write failing test：`log_sandbox_exec` 抛异常时 `run_code` 仍正常返回代码执行结果，并记录一条警告（mock `log_sandbox_exec` 抛异常，断言返回值正常 + warning）。看到红
- [x] 6.2 Implement：`run_code` 内 trace 写入包 try/except，失败 `logger.warning` 不 re-raise，看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
