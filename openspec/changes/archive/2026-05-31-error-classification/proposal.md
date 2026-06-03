## Why

主循环（`agent_loop.run()` / `run_stream()`）遇到运行时错误时，处理方式分散且不统一：`_call_with_fallback` 在 `_call_with_fallback` 内部直接对 `RateLimitError` / 503 做 fallback 重试；工具崩溃由 `_safe_dispatch` 归一化为错误字符串；其它错误（上下文超限、认证失败、未来的工具超时 / MCP 断连 / 沙箱 OOM）则各自散落或尚无归口。没有一个统一的「错误 → 分类 → 恢复策略标志位」的中间层，导致每加一类错误都要在主循环里重复解析异常内容、判断该不该重试 / 压缩 / 切模型。

这是 AR5（错误分类与重试策略）。它是波次 2 多个功能（工具超时保护、MCP 重连、沙箱错误处理）的**接口地基**：这些功能产生的错误都需要被归一化到统一分类，主循环才能用一致的方式响应，而非各写各的判断分支。

## What Changes

- 新增**错误分类层**（建议 `src/fleetent/error_classifier.py`）：把运行时异常/错误归一化为一组固定分类码：`rate_limit` / `context_overflow` / `tool_timeout` / `tool_crash` / `mcp_disconnect` / `sandbox_oom` / `sandbox_timeout` / `auth_failed` / `unknown`。
- 每个分类挂载一组**恢复策略标志位**：`should_retry`（是否重试）/ `should_compress`（是否触发压缩后重试）/ `should_switch_model`（是否切换备用模型）。
- 提供 `classify(error) -> ErrorCategory` 纯函数：依据异常类型/状态码/错误特征归类，识别不出则归 `unknown`。
- 提供 `ErrorClassification` 数据结构承载「分类码 + 三个标志位」；主循环**只读标志位**决定动作，不再在循环体里重复解析异常内容。
- 形式化既有 `rate_limit → fallback` 行为：`RateLimitError` / 503 归类为 `rate_limit`（`should_retry=True` + `should_switch_model=True`），与现 `_call_with_fallback` 语义对齐；本次将判定口径收口到分类层，便于后续扩展。
- 分类发生时将**分类码写入运行日志（trace）**，供统计「任务遇到哪类错误」。
- 为波次 2 的 `tool_timeout` / `mcp_disconnect` / `sandbox_oom` / `sandbox_timeout` 预留分类码与标志位定义（**本次仅定义分类与标志位，不实现各错误源的触发与恢复动作**）。

## Capabilities

### New Capabilities
- `agent-error-classification`: 运行时错误的统一分类与恢复策略标志位——`classify()` 把异常归一化为固定分类码，每类挂载 `should_retry` / `should_compress` / `should_switch_model` 标志位；主循环只读标志位，不重复解析错误内容；分类码写入 trace。本次覆盖分类层与标志位定义，并形式化既有 `rate_limit → fallback`；其余分类码为波次 2 预留。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。model fallback 的可观察行为不变，仅内部判定口径收口到分类层。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/error_classifier.py`（`ErrorCategory` 枚举 + `ErrorClassification` 数据类 + `CLASSIFICATION_TABLE` + `classify()`）。
  - 修改 `src/fleetent/agent_loop.py`：`_call_with_fallback` / `_stream_with_fallback` 的 429/503 判定改为经 `classify()` 读 `should_switch_model` 标志位；fallback 耗尽抛出的异常先 `classify()` 取分类码用于 trace。
  - `eval_logger.log_run` 调用补充 `error_category` 字段（trace 写入）。
- **配置**：无新增 Settings 字段（分类表为静态映射，不需部署级配置）。
- **测试**：新增 `tests/test_error_classifier.py`；`tests/test_agent_loop.py` 补充「fallback 经分类层判定」用例。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：工具 dispatch、permission_gate、上下文压缩、终止框架的既有行为；不引入新依赖。
