## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 AR1 框架接口：`termination.py` 的 `TerminationChecker` Protocol（`check(state: LoopState) -> StopReason | None`）、`TerminationController.register` / `should_stop`、`StopReason.loop_detected` 已存在，确认本 change 仅新增 checker + 扩展 `LoopState`
- [x] 1.2 核实主循环工具调用落点：`run()`（agent_loop.py 行 325-384）与 `run_stream()`（行 566-574）的工具分发处，确认可在每次工具调用后取到 `(tool_name, arguments, 工具结果文本, 是否成功)` 记入 `LoopState`——信号 B 需要结果文本与成功标志（结果即 `_safe_dispatch` 归一化后的字符串、`failed` 标志），确认该落点能同时拿到三者
- [x] 1.3 核实 `_build_controller`（行 46-59）注册顺序，确认在既有 checker 之后追加 `LoopDetectionChecker` 不改变既有终止优先级
- [x] 1.4 核实 `message_hygiene.sanitize` 对连续同角色消息的处理与 `maybe_compress` 的 `keep_tail` 行为，确认 design D4 已定死的警告消息角色（`user`）与 D4b 警告对压缩轮的可见性落点可落实
- [x] 1.5 核实 `config.Settings` 字段添加方式（config.py 行 7-25），确认新增 `agent_loop_repeat_threshold: int` 默认 3 即可经 `.env` / `config/settings.yaml` 覆盖

## 2. 参数指纹与结果摘要纯函数（loop_detector.py）

- [x] 2.1 Write failing tests for `arg_fingerprint` 归一化纯函数：`tests/test_loop_detector.py` 断言键序不同但语义相同的 JSON 参数得到同一指纹；非法 JSON 退化为对原始字符串取指纹；不同参数得到不同指纹。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `arg_fingerprint`（按 D2：解析→排序 key→序列化；失败退化），看到绿
- [x] 2.3 Write failing tests for `result_digest` 纯函数：超长结果按「截首尾各 1KB 再哈希」得到稳定 digest；首尾相同、中段不同的两个超长结果在截断口径下若落入同一首尾片段得同一 digest（确认截断口径），实质不同的结果得不同 digest；空结果有确定 digest。看到红
- [x] 2.4 Implement `result_digest`（截首尾限长→哈希），看到绿

## 3. LoopState 历史扩展（termination.py）

- [x] 3.1 Write failing tests：`tests/test_termination.py` 断言 `LoopState` 含工具调用历史字段（每项为 `(tool_name, arg_fingerprint, result_digest, success)` 四元组）与「警告已注入」标志，默认空 / False，且现有 checker 行为不受影响。看到红
- [x] 3.2 Implement `LoopState` 扩展（默认空 list / False，向后兼容；历史项含结果 digest 与成功标志；窗口 FIFO 截断），看到绿

## 4. LoopDetectionChecker 两段式判定（loop_detector.py）

- [x] 4.1 Write failing tests for 信号 A + 第一段（警告）：同一 `(tool_name, arg_fingerprint)` 达到阈值且「警告未注入」时，checker 请求注入警告但**不**返回 `loop_detected`。看到红
- [x] 4.2 Implement 信号 A 判定 + 第一段，看到绿
- [x] 4.3 Write failing tests for 信号 B（结果停滞）：同一 `tool_name` 的**成功**调用产出相同 `result_digest` 达阈值（即便每次 `arg_fingerprint` 不同）即命中；失败结果不计入信号 B；结果每次不同时信号 B 不命中。看到红
- [x] 4.4 Implement 信号 B 判定（成功 + 同 digest 计数，排除失败结果），看到绿
- [x] 4.5 Write failing tests for 第二段（终止）：警告已注入后任一信号再次达阈值，checker 返回 `StopReason.loop_detected`；参数与结果均不同（两信号无重复）时永不命中。看到红
- [x] 4.6 Implement 第二段判定（任一信号触发），看到绿
- [x] 4.7 Write failing tests for 阈值注入与可选忽略表：传入小阈值（如 2）改变命中所需重复次数；`loop_detect_ignore_arg_keys` 默认空（不剔除任何键）、置非空时算 `arg_fingerprint` 前剔除指定键。看到红
- [x] 4.8 Implement 阈值注入（构造参数 + 从 Settings 解析默认）与忽略表（默认空），看到绿

## 5. 接入主循环（agent_loop.py）

- [x] 5.1 Write failing tests for `run()`：(a) 信号 A——持续返回同一工具+同参数调用 → 注入警告 → 仍重复 → `loop_detected` 终止并 `log_run(stop_reason=loop_detected)`；(b) 信号 B——同一工具但参数每次不同、结果相同 → 同样触发两段式;(c) 参数与结果都每次不同时不触发。mock `get_async_client_and_config` 与 `_safe_dispatch` 结果。看到红
- [x] 5.2 Implement `run()` 接入：`_build_controller` 注册 `LoopDetectionChecker`；每次工具调用后把 `(tool_name, arg_fingerprint, result_digest, success)` 记入 `LoopState`；checker 请求注入时 append 警告消息并标记。看到绿
- [x] 5.3 Write failing tests for `run_stream()`：同等行为；注入警告不向客户端 yield 额外事件；`loop_detected` 提前收尾。看到红
- [x] 5.4 Implement `run_stream()` 接入，看到绿
- [x] 5.5 Write failing test for 警告轮恰逢压缩的可见性（D4b）：注入警告的那一轮同时触发 `maybe_compress` 时，警告内容仍出现在送往下一次 LLM 调用的消息序列中（未被压缩摘要吞掉），警告以 `user` 角色存在。mock `maybe_compress` 使其在该轮命中。看到红
- [x] 5.6 Implement 警告在压缩之后 / 纳入 `keep_tail` 的可见性保证，看到绿

## 6. 配置项（config.py + settings.yaml.example）

- [x] 6.1 Write failing test：`Settings().agent_loop_repeat_threshold` 默认 3、可被环境变量覆盖；`Settings().loop_detect_ignore_arg_keys` 默认空列表。看到红
- [x] 6.2 Implement：`config.py` 新增 `agent_loop_repeat_threshold` 与 `loop_detect_ignore_arg_keys`（默认空）字段；`config/settings.yaml.example` 补注释示例。看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误模式
