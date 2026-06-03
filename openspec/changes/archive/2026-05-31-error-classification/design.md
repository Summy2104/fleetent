## Context

`agent_loop.py` 当前的错误处理是分散的：`_call_with_fallback`（行 74）与 `_stream_with_fallback`（行 102）各自捕获 `RateLimitError` 与 `APIStatusError`（仅 `status_code == 503`）并切换 fallback 模型；`_safe_dispatch`（行 57）把工具崩溃归一化为 `("tool execution error: ...", failed=True)` 字符串。没有任何地方把「这是哪类错误、该不该重试 / 压缩 / 切模型」收口成统一判定。

AR1 终止框架（已合入 `termination.py`）确立了「策略化 + 标志位驱动主循环」的模式。本 change 沿用同一思路解决错误维度：错误分类层产出标志位，主循环只读标志位。

本 change 是 AR5，也是波次 2（AR：工具超时保护 / MCP 重连 / 沙箱错误处理）的接口地基。这些后续功能的错误都要归一化到本层定义的分类码，主循环才能一致响应。因此本次首要目标是**把分类码与标志位的契约定准**，避免后续每加一个错误源都改主循环。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（分类表为模块级不可变常量，可被测试只读引用）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；测试 mock LLM。

## Goals / Non-Goals

**Goals:**
- 提供 `classify(error) -> ErrorClassification` 纯函数，把异常归一化为固定分类码。
- 定义全部 9 个分类码及其 `should_retry` / `should_compress` / `should_switch_model` 标志位。
- 主循环的 429/503 fallback 判定改为读分类层标志位，可观察行为不变。
- 分类码写入 trace。
- 为波次 2 错误源（tool_timeout / mcp_disconnect / sandbox_oom / sandbox_timeout）预留分类码与标志位，供其接入。

**Non-Goals:**
- 不实现各错误源的**触发**与**恢复动作**（工具超时取消、MCP 重连、沙箱清理等各自后续 change）。
- 不实现 `context_overflow` 的「压缩后重试」执行逻辑（仅定义标志位 `should_compress=True`，主循环消费它是后续 AR）。
- 不改动 model fallback 的可观察行为、工具 dispatch、permission_gate、终止框架。
- 不引入新依赖、不新增 Settings 字段。

## Decisions

### D1：静态分类表 + 纯函数 classify，主循环只读标志位
新增 `src/fleetent/error_classifier.py`：
- `ErrorCategory`：`str` 枚举，含全部 9 个分类码。
- `ErrorClassification` 数据类（frozen）：`category: ErrorCategory`、`should_retry: bool`、`should_compress: bool`、`should_switch_model: bool`。
- `CLASSIFICATION_TABLE: dict[ErrorCategory, ErrorClassification]`：模块级不可变常量，分类码 → 标志位的单一事实来源。
- `classify(error: Exception) -> ErrorClassification`：依据异常类型/状态码归类，查表返回；识别不出归 `unknown`。

**为何**：分类（识别）与策略（标志位）分离，标志位集中在一张表里一目了然、易审计；主循环不再在多处 `isinstance` + 状态码判断里夹带「该不该重试」的隐性逻辑——它只调用 `classify()` 然后读 `clf.should_switch_model`。这正是 AR1 已验证的「标志位驱动循环」模式在错误维度的复用。
**Alternatives**：①每个分类一个 checker 对象（仿 termination 的 checker）——被否，错误分类是「一个输入映射到一个分类」的纯查表问题，不是「多个独立策略依次判定」，checker 列表是过度设计；②在主循环里继续散写 `isinstance` 判断——被否，正是本 change 要消除的重复解析。

### D2：分类判据（本次可判定的分类）
- `rate_limit`：`isinstance(error, RateLimitError)`，或 `APIStatusError` 且 `status_code == 429`。标志位 `should_retry=True` / `should_switch_model=True` / `should_compress=False`，与现 `_call_with_fallback` 对 429 的处理对齐。
- 503（服务不可用）：归入 `rate_limit` 类（同 `should_switch_model=True`），与现 `_stream_with_fallback` 对 503 切 fallback 的行为一致——不为 503 单列分类码，避免分类码膨胀且语义重合。
- `context_overflow`：依据 OpenAI 兼容错误中的上下文超限特征（`APIStatusError` 且错误体含上下文长度超限标识，如 `context_length_exceeded` code）。标志位 `should_compress=True` / `should_retry=True` / `should_switch_model=False`。
- `auth_failed`：`APIStatusError` 且 `status_code` in `{401, 403}`。标志位全 False（不重试，向用户报错）。
- `tool_crash`：通用工具执行异常归此类。标志位 `should_retry=False` / `should_compress=False` / `should_switch_model=False`（结果交由 AI 决策，主循环不自动重试）。
- `unknown`：以上都不匹配。标志位全 False（默认不重试，向用户报错）。

**为何**：判据全部基于异常类型 + 状态码 + 错误体特征，可单测、无副作用；503 并入 rate_limit 与现状语义一致。
**Open**：`context_overflow` 与 `auth_failed` 的精确错误体特征需在实现首步用真实 OpenAI 兼容 SDK 异常结构核实（见 Open Questions）。

### D3：波次 2 预留分类码（本次定义标志位，不实现触发）
`tool_timeout` / `mcp_disconnect` / `sandbox_oom` / `sandbox_timeout` 在 `ErrorCategory` 与 `CLASSIFICATION_TABLE` 中定义齐全（按 agent-runtime.md 的策略表设定标志位）：
- `tool_timeout`：标志位全 False（返回超时结果，不中断循环——由调用方据此构造结果，不自动重试）。
- `mcp_disconnect`：`should_retry=True`（尝试重连，失败降级——重连动作由 mcp_client 侧后续实现）。
- `sandbox_oom` / `sandbox_timeout`：标志位全 False（返回失败结果并告警/清理——动作由 sandbox 侧后续实现）。

但**不**在本 change 中接入任何产生这些异常的代码路径，`classify()` 也不会主动返回它们（除非未来的错误源传入对应异常类型）。
**为何**：先把契约（分类码 + 标志位）定准，波次 2 各功能直接复用，不再反复改本层与主循环。
**Alternatives**：等波次 2 时再逐个加分类码——被否，会导致每个后续 change 都修改分类表的枚举与判据，本 change 的「接口地基」定位要求一次定齐。

### D4：trace 写入分类码
fallback 重试耗尽抛出异常前，主循环对该异常 `classify()` 取 `category`，经 `log_run` 新增的 `error_category` 参数写入 trace（默认 None 向后兼容）。
**为何**：复用现有唯一 trace 出口，改动最小；与 AR1 的 `stop_reason` 写入方式一致。

### D5：与 fallback 既有代码的协调
`_call_with_fallback` / `_stream_with_fallback` 的 `except` 分支由「`isinstance` + 硬编码 `status_code == 503`」改为：捕获到异常后 `clf = classify(exc)`，若 `clf.should_switch_model` 则记为 `last_exc` 继续试下一个模型，否则 `raise`。可观察行为与现状等价（429/503 → 切 fallback；其它 → 抛出）。
**为何**：消除散落的状态码硬编码，把「该不该切模型」的判断收口到分类层；同时保持现有用例绿。

## Risks / Trade-offs

- [分类判据与真实 SDK 异常结构不吻合（尤其 context_overflow / auth_failed）] → 实现首步先用 `openai` SDK 的异常类与状态码核实判据，必要时以状态码为主、错误体特征为辅；识别不出一律安全归 `unknown`（全 False，不误重试）。
- [预留分类码被误认为已实现] → spec 明确「未接入错误源的分类码不会被主动返回」；design D3 标注；加守卫测试断言 `classify()` 对当前可达异常只产出本次可判定的分类。
- [503 并入 rate_limit 可能让 trace 统计无法区分限流与服务不可用] → 本次接受该粒度（与现状语义一致）；若后续需区分，可在不改标志位语义的前提下细分分类码。
- [重构 fallback 判定可能引入行为漂移] → 判定全部收敛到 `classify()`，fallback 函数仅读 `should_switch_model`；保留并扩展 `tests/test_agent_loop.py` 既有 429/503 用例确保等价。

## Open Questions

- `context_overflow` 在 OpenAI 兼容后端的确切错误体特征（`code` 字段值 / 消息文本）——实现首步用 SDK 异常结构与现有 mock 核实后定 `classify()` 判据。
- `auth_failed` 是否需覆盖 SDK 的 `AuthenticationError` 子类而非仅状态码——实现时确认 `openai` SDK 异常层级后决定。
