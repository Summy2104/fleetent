## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实真实泄漏路径：assistant 消息的 `tool_calls[].function.arguments`（原始 JSON）经 `agent_loop.py` 行 601 `messages.append(msg.model_dump())` 进入 `messages`，再由 `log_run`（行 697-700）整体交 `eval_logger._serialize` 落 trace；确认脱敏须覆盖这一输入形态，且 dispatch 不经手这份消息 JSON
- [x] 1.2 核实 `eval_logger` 序列化层：`_serialize`（行 146）→ `_placeholder_images`（行 154）的范式（序列化时占位敏感内容、用 `{**msg, ...}` 新建不改原对象）；确定 tool_call 脱敏插在同一层、同范式
- [x] 1.3 核实 `sandbox_secrets.is_sensitive_name` 与 `SENSITIVE_TOKENS`（模块级、可 monkeypatch、大小写不敏感子串、仅名过滤）的签名与语义；确认本 change 直接复用、不在 `eval_logger` 复制规则
- [x] 1.4 核实 OpenAI assistant 消息 `model_dump()` 中 `tool_calls[].function.arguments` 的形态（JSON 字符串）；确认解析容错（非法 JSON 退化为既有行为、不抛异常）

## 2. trace 层 tool_call 敏感名参数值脱敏（eval_logger，与 _placeholder_images 同范式）

- [x] 2.1 Write failing test for tool_call 敏感名参数脱敏：序列化一条含 `tool_calls[].function.arguments` 的 assistant 消息（含 `api_key` / `password` 键），写入 trace 的该参数值被替换为占位符。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：在 `eval_logger` 序列化路径扩展——序列化 assistant `tool_calls` 时解析 `function.arguments`，键名命中 `sandbox_secrets.is_sensitive_name` 的值替换为占位符（与 `_placeholder_images` 同层、用新建表示不改原对象）。看到绿
- [x] 2.3 Write failing test for 非敏感名不变：tool_call 参数名未命中（如 `query` / `path`）时，trace 中该值保持原样。看到红/绿确认
- [x] 2.4 Write failing test for 无 tool_calls 消息不受影响：普通 user/assistant 文本消息、含图片块的消息序列化行为与既有 `_serialize` / `_placeholder_images` 一致。看到绿确认无回归

## 3. 作用域钉死：仅 trace，不动 session / 运行时对象

- [x] 3.1 Write failing test for 不污染原对象：脱敏后断言传入序列化层的原始消息对象未被改写（tool_call 原值仍在原对象中），运行时工作上下文不受影响。看到红
- [x] 3.2 Implement：脱敏产出新表示（`{**msg, ...}` 新建），不改原 `messages` 元素。看到绿
- [x] 3.3 Write failing/regression test for session 不脱敏：session 持久化的消息保留原始明文参数值（脱敏不经过 session 写入路径，仅在 trace 序列化处发生）。看到绿确认

## 4. 复用 SB5 规则 + 仅名过滤局限固化

- [x] 4.1 Write failing test for 复用 SB5 规则：monkeypatch `sandbox_secrets.SENSITIVE_TOKENS` 后，trace 层 tool_call 脱敏命中判定随之变化（证明同一套规则、未在 `eval_logger` 另立常量）。看到红/绿确认复用
- [x] 4.2 Write failing test for 仅名过滤局限：非敏感名参数（如 `note`）的值文本内嵌密钥时不被脱敏（固化已知边界，与 SB5 一致）。看到红/绿确认边界

## 5. 路径穿越保护：重定向，不在本 change 实现

- [x] 5.1 在 design/proposal 注明路径穿越保护下沉到各「处理路径的工具」（共享 `safe_path()` 在 `open()` 处 fail-closed），不在 dispatch、不在本 change 实现；本 change 不产出 safe_path 代码或测试（仅文档重定向，无实现任务）

## 6. 收尾

- [x] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，LLM 调用全 mock，trace 路径隔离 tmp_path），无回归
- [x] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 6.3 `uv run mypy src` 无新增错误
