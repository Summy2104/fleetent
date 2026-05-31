## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `openai` SDK 异常层级：`RateLimitError` / `APIStatusError` 的 `status_code` 字段；`AuthenticationError` 是否独立子类；`context_length_exceeded` 在错误体中的呈现（`code` / message），据此定 `context_overflow` 与 `auth_failed` 判据
- [ ] 1.2 核实 `_call_with_fallback` / `_stream_with_fallback` 现状对 429/503 的处理（agent_loop.py 行 74-129），确认改为读 `should_switch_model` 后行为等价
- [ ] 1.3 确认 `log_run` 签名（eval_logger.py 行 14-24），新增末位 kw 参数 `error_category: str | None = None` 即向后兼容

## 2. 分类码与标志位（error_classifier.py）

- [ ] 2.1 Write failing tests for `ErrorCategory` 枚举与 `ErrorClassification` 数据类：`tests/test_error_classifier.py` 断言枚举含全部 9 个分类码；`ErrorClassification` 含 `category` / `should_retry` / `should_compress` / `should_switch_model` 字段。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `ErrorCategory`（StrEnum）、`ErrorClassification`（frozen dataclass），看到绿
- [ ] 2.3 Write failing tests for `CLASSIFICATION_TABLE`：表中含全部 9 个分类码；`rate_limit` 为 retry+switch_model；`context_overflow` 为 compress；`auth_failed` / `unknown` / `tool_crash` 全 False；预留码（tool_timeout/mcp_disconnect/sandbox_oom/sandbox_timeout）存在且标志位符合 agent-runtime.md 表。看到红
- [ ] 2.4 Implement `CLASSIFICATION_TABLE`（模块级不可变常量），看到绿

## 3. classify() 判定函数

- [ ] 3.1 Write failing tests for `classify()`：`RateLimitError` → rate_limit；429/503 `APIStatusError` → rate_limit；401/403 → auth_failed；context 超限异常 → context_overflow；通用工具异常 → tool_crash；其它 → unknown。看到红
- [ ] 3.2 Implement `classify()`（按 D2 判据查表返回；识别不出归 unknown），看到绿
- [ ] 3.3 Write failing test 守卫 `test_classify_never_yields_reserved`：对当前可达 LLM 异常集，`classify()` 不返回任何预留分类码。看到红
- [ ] 3.4 Implement 使守卫通过（确保预留码无对应判据分支），看到绿

## 4. 接入 fallback 判定（agent_loop.py）

- [ ] 4.1 Write failing tests：`_call_with_fallback` / `_stream_with_fallback` 对 429/503 经 `classify()` 读 `should_switch_model` 切 fallback；非可切换错误直接抛出。mock `get_async_client_and_config`。看到红
- [ ] 4.2 Implement：fallback 函数 `except` 分支改为 `clf = classify(exc)`，依 `clf.should_switch_model` 决定续试或 `raise`，行为与现状等价。看到绿

## 5. trace 写入分类码

- [ ] 5.1 Write failing tests：fallback 耗尽抛异常时 `log_run` 收到对应 `error_category`；正常运行不写该字段。看到红（先验证 log_run 尚未接收 error_category）
- [ ] 5.2 Implement：`log_run` 增加 `error_category: str | None = None`（默认 None 向后兼容，非 None 写入 entry）；`run()` / `run_stream()` 在 fallback 异常出口对异常 `classify()` 取 category 传入。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误模式
