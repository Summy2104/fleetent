## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实工具结果写回点：`agent_loop.run()`（agent_loop.py 行 676）与 `run_stream()`（行 947）的 `messages.append({"role": "tool", ...})`，`content` 为 `dispatch()` 返回的完整 `result`，未经长度约束
- [x] 1.2 核实字节口径与 SB6 一致：`sandbox_client.py` 已用 `len(s.encode("utf-8"))`；本 change 截断阈值与切分一律用 `len(s.encode("utf-8"))`，不用字符数 / token。默认阈值定为 ~40KB（10k tokens 量级），**不为迁就 SB6（stdout 50KB + stderr 10KB = 60KB）抬高**。参照 `loop_detector.result_digest`（行 70-85）头尾保留先例（仅参照，digest 不写回 messages）
- [x] 1.4 核实 `@tool` 平行元数据范式：`tool_registry` 已有 `_risk_levels` / `_connectors` 模块级 dict 与 `risk_level` / `connector` 装饰器参数，均不进入 LLM schema；本 change `self_truncates` 照此范式新增。确认 `run_code` 由 SB6 独占截断、应声明 `self_truncates=True` 对 T4 豁免（T4 不二次截 `run_code`，二者无数值耦合）
- [x] 1.3 确认截断只作用于写入 `messages` 的副本：`dispatch()` 返回值不改（保 `loop_detector.result_digest` 去重、`run_stream` 的 `tool_result` SSE 事件看到的仍是原始结果）；`eval_logger` trace 序列化 `messages` 故记录的是截断后内容（= LLM 所见，与本决策一致）；阈值常量可 `monkeypatch`，不引入全局可变状态

## 2. 截断函数与默认阈值（tool_result_truncation.py）

- [x] 2.1 Write failing tests for 截断函数：阈值内结果原样返回；超阈值结果被截断且字节数（`len(encode("utf-8"))`）不超过阈值；未传阈值时取模块级 `MAX_TOOL_RESULT_BYTES` 默认。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `truncate_tool_result(result, max_bytes=None)` 与模块级 `MAX_TOOL_RESULT_BYTES`（安全默认、可 monkeypatch），看到绿

## 3. 头尾保留 + breadcrumb 策略（tool_result_truncation.py）

- [x] 3.1 Write failing tests for 头尾 + breadcrumb：截断结果以原始头部开始、原始尾部结束，中间含标明「原始字节数 / 省略字节数」的 breadcrumb；头 + 尾 + breadcrumb 之和不超过阈值。看到红
- [x] 3.2 Implement 头尾保留 + breadcrumb 占位（预算分配保证不反超阈值），看到绿

## 4. 多字节字符安全切分（tool_result_truncation.py）

- [x] 4.1 Write failing tests for 多字节边界：字节预算边界落在多字节字符（如中文）中段时回退到完整字符边界，截断结果为合法 UTF-8、不含半个字符。看到红
- [x] 4.2 Implement 切点回退到完整 UTF-8 字符边界，看到绿

## 5. 阈值可注入（tool_result_truncation.py）

- [x] 5.1 Write failing tests for 阈值可注入：按次传入更小阈值生效；`monkeypatch MAX_TOOL_RESULT_BYTES` 改变默认行为；默认值为 ~40KB（10k tokens 量级）。看到红
- [x] 5.2 Implement 按次阈值覆盖（默认 ~40KB，可 monkeypatch），看到绿

## 5b. `self_truncates` opt-out（tool_registry.py）

- [x] 5b.1 Write failing tests for `self_truncates` 元数据：`@tool(self_truncates=True)` 声明的工具经 `is_self_truncating(name)` 返回 `True`，未声明默认 `False`；`self_truncates` 与 `risk_level` / `connector` 平行存放、**不出现在 LLM schema** 中（断言 `get_schemas()` 输出不含该字段）。看到红
- [x] 5b.2 Implement `@tool` 新增 `self_truncates: bool = False`（存入模块级 dict，平行于 `_risk_levels` / `_connectors`，不进 schema）+ `is_self_truncating(name) -> bool`；`run_code` 声明 `self_truncates=True`。看到绿

## 6. 接入工具结果写回点（agent_loop.py）

- [x] 6.1 Write failing tests for run() 写回截断：`run()` 中超大工具结果写入 `messages` 的 `tool` 消息已被截断（字节数不超阈值、含 breadcrumb），trace 记录的即此截断内容（与写入 `messages` 的一致），`dispatch()` 返回值不变。LLM mock、路径隔离 tmp_path。看到红
- [x] 6.2 Implement：`run()`（行 676）写回前对非 `self_truncates` 工具的 `result` 调 `truncate_tool_result`，看到绿
- [x] 6.3 Write failing tests for run_stream() 写回截断：`run_stream()` 写入 `messages` 的 `tool` 消息被截断，但 `tool_result` SSE 事件仍发原始结果（截断只作用于 messages 副本）。看到红
- [x] 6.4 Implement：`run_stream()`（行 947）写回前对非 `self_truncates` 工具的 `result` 调 `truncate_tool_result`（SSE 事件仍用原始 `result`），看到绿
- [x] 6.5 Write failing tests for 自截断工具豁免：声明 `self_truncates=True` 的工具（如 `run_code`）返回超 T4 阈值的大结果时，`run()` 与 `run_stream()` 写入 `messages` 的 `tool` 消息**未被 T4 截断**（原样写回、无 T4 breadcrumb，T4 不碰它）；未声明的工具仍被截断。LLM mock、路径隔离 tmp_path。看到红
- [x] 6.6 Implement：写回前用 `is_self_truncating(tool_name)` 判断，`True` 则跳过 `truncate_tool_result`、原样写回（`run()` 行 676 与 `run_stream()` 行 947 两处一致），看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
