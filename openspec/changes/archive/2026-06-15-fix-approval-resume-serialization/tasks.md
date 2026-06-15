## 1. dispatch 不污染调用方 args（根因）

- [x] 1.1 写测试（红）：`registry.dispatch(name, {"x":"v"}, tool_context=ctx)`（opt-in tool）调用后，传入的同一 dict **不含** `tool_context`/`cancel_token` 键；工具仍收到注入（行为不变）
- [x] 1.2 实现（绿）：`registry.dispatch` args 为 dict 时 `kwargs = dict(arguments_json)`（复制后注入），字符串路径不变

## 2. args_summary 构建容错（纵深防御）

- [x] 2.1 写测试（红）：`build_tool_args_summary({"a": <不可序列化对象>})` 返回字符串、不抛
- [x] 2.2 实现（绿）：`observability.build_tool_args_summary` 的 `json.dumps` 加 `default=str`

## 3. 恢复执行回归

- [x] 3.1 写测试（红→绿）：模拟恢复执行——以 dict 入参经 `dispatch` 注入 tool_context 后调用 `_record_resumed_tool_call`/`build_tool_args_summary`，断言不抛、args_summary 不含 ToolContext（覆盖 resume 崩溃场景）

## 4. 收尾验证

- [x] 4.1 受影响层单测全绿（registry / traces / approval_resume 相关）
- [x] 4.2 `make test-pr` 全绿（无新增失败）
- [x] 4.3 `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 4.4 `openspec validate fix-approval-resume-serialization --strict` 通过
- [x] 4.5 `uv run mypy src` 无新增错误；改动文件 ruff 净
