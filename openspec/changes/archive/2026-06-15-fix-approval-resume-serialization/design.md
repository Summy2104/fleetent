## Context

审批恢复路径：`im_gateway.normalizer._resume_pending_in_session` → `runtime.approval_resume.resume_pending_approval` → `_execute_tool(tool_name, entry["tool_args"], tool_context)`，其中 `entry["tool_args"]` 是从持久化条目读出的 **dict**。`_execute_tool` 在 `finally` 调 `_record_resumed_tool_call` → `build_tool_args_summary(tool_args)`（trace-tool-spans：恢复执行也要记 tool_call span）。

`registry.dispatch(name, arguments_json, ..., tool_context=...)`：
```python
kwargs = arguments_json if isinstance(arguments_json, dict) else json.loads(arguments_json)
...
if cancel_token is not None and _accepts_cancel_token(fn): kwargs[_CANCEL_TOKEN_PARAM] = cancel_token
if tool_context is not None and _accepts_tool_context(fn): kwargs[_TOOL_CONTEXT_PARAM] = tool_context
```
args 为 dict 时 `kwargs` 与调用方**同一引用**，注入 `tool_context`/`cancel_token` 即**原地污染** `entry["tool_args"]`。随后 `build_tool_args_summary` 对含 `ToolContext` 的 dict `json.dumps` → `TypeError`，未被捕获 → 冒泡中断 resume（normalizer 的 save/route 崩、按钮 handler 记 `approval_button_resume_failed`）。

正常 loop 路径 args 是 LLM 给的 JSON 字符串，`json.loads` 每次产新 dict，dispatch 的注入只在该新 dict 上，不回污染调用方 → 不触发。故 bug 仅在 resume（dict 入参 + 入参被 finally 复用）显现。预存，独立于本批接收方展示/回执改动。

## Goals / Non-Goals

**Goals:**
- 审批恢复在所有续跑路径下不再因 args 序列化崩溃。
- `dispatch` 对调用方传入的 args 映射保持**纯函数**语义：out-of-band 注入（tool_context/cancel_token）只进本次 kwargs，绝不回写调用方 dict。
- tool_call args_summary 构建对任意不可序列化值稳健（trace 记录失败不影响 run，落实 trace-tool-spans 既有不变量到本路径）。
- out-of-band 注入的上下文不出现在持久化 args_summary（摘要只反映模型入参）。

**Non-Goals:**
- 不改审批触发面/风险分级；不改 dispatch 的注入语义（仍按 opt-in 注入），只去掉副作用。
- 不改 trace 事件 schema 或脱敏基线。
- 不动本批已合的接收方展示/回执（#265）。

## Decisions

1. **`dispatch` 复制 dict args（根因修复）**：
   `kwargs = dict(arguments_json) if isinstance(arguments_json, dict) else json.loads(arguments_json)`。
   注入写入的是副本，调用方的 `entry["tool_args"]` 永不被改写。一行、零行为变化（kwargs 内容不变，仅不再别名调用方 dict）；MCP 包装分支（接收 kwargs）同样受益。

2. **`build_tool_args_summary` 容错（纵深防御）**：
   `json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)`。任何残留的不可序列化值降级为其 `str()` 而非抛异常——保证 args_summary 永不使 trace 记录崩溃。与脱敏/截断顺序不变。

3. 两层独立生效：①使注入不再污染入参（根因）；②即便未来有其他不可序列化入参，trace 摘要也不崩（防御）。resume 因此稳健。

4. **TDD**：
   - 红：`dispatch(name, {"x":1}, tool_context=ctx)` 调用后，传入的 dict **不含** `tool_context`/`cancel_token` 键（未被污染）。
   - 红：`build_tool_args_summary({"a": <不可序列化对象>})` 返回字符串、不抛。
   - 红：`_record_resumed_tool_call`/resume 在工具经 dict 入参 dispatch 后，args_summary 不含 ToolContext、不抛（回归）。
   - 绿：实现上面两处。

## Risks / Trade-offs

- **dispatch 复制 dict 的开销**：浅拷贝一层 dict，可忽略；且仅 dict 入参路径（loop 主路径是字符串，行为完全不变）。
- **`default=str` 可能让某些对象以 repr 入摘要**：args_summary 本就是有损摘要（已脱敏+截断），用 `str()` 兜底优于崩溃；且根因修复后正常不会再有注入对象进摘要。
- 范围聚焦单一预存缺陷，不夹带其他改动。
