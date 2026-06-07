## 1. read_skill 拒绝写审计日志

- [x] 1.1 Write failing test（unit）：`read_skill` 拒绝 audit_blocked skill 时调 `audit_log.write_audit`，action=`skill.read_refused`、target=skill 名（mock write_audit + _index 含 audit_blocked entry）
- [x] 1.2 Write failing test（unit）：带 tool_context 时审计 detail 含 session_id/agent_name
- [x] 1.3 Write failing test（unit）：正常读取（非 audit_blocked）不写 skill.read_refused 日志
- [x] 1.4 Write failing test（unit）：write_audit 抛异常时被捕获，read_skill 仍返回拒绝文本
- [x] 1.5 运行确认红：`uv run pytest tests/unit/test_builtin_tools_skill.py -x -q`
- [x] 1.6 实现：`read_skill(name, tool_context=None)` 在 audit_blocked 分支调 `audit_log.write_audit(...)`，try/except 捕获写入异常记 warning
- [x] 1.7 运行确认绿：同上命令

## 2. 验证与收尾

- [x] 2.1 运行相关测试：`uv run pytest tests/unit/test_builtin_tools_skill.py tests/unit/test_tools.py -q`
- [x] 2.2 运行全套测试：`uv run pytest -x -q`
- [x] 2.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/tools/builtin_tools.py`
- [x] 2.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
