# Tasks — trace-tool-spans

> 每个实现任务严格 TDD：先写测试见红，再实现见绿。涉及真实 sqlite 的测试放 integration（tmp_path 隔离）。

## 1. trace 记录 API

- [x] 1.1 测试：`record_tool_call(run_id, session_id, payload)` 落库形状（event_type/payload 字段/写入失败仅 warning 不抛）——integration，先红
- [x] 1.2 实现：`observability/traces.py` 新增 tool_call 记录函数 + public API 导出——绿
- [x] 1.3 测试：args_summary 脱敏与 2KB 截断（secret 字段不落明文、超限带截断标记）——unit，先红
- [x] 1.4 实现：复用 tool-arg-secret-redaction 基线 + 截断——绿

## 2. loop 挂接

- [x] 2.1 测试：backfill 真实执行点产生事件、placeholder（审批挂起/guardrail deny）不产生、失败执行 failed=true、run 与 run_stream 两路一致——integration（mock LLM），先红
- [x] 2.2 实现：backfill 阶段（post_tool_use 同点）挂接 record_tool_call，记录耗时与 risk——绿

## 3. session 绑定

- [x] 3.1 测试：agent_run_completed / injected_context / skill_hit / tool_call 携带 session_id；按 session_id 查询取回完整事件序列；恢复 run 归属原会话——integration，先红
- [x] 3.2 实现：trace 记录函数加可选 session_id 参数（默认 None 兼容存量），loop/normalizer 调用点补传——绿

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 无新增失败 + mypy 无新增错误
- [x] 4.2 真机验证：my-bot 跑一轮含工具调用的对话，SQL 按 session_id 重建轨迹核对（自动化替代：真实落盘 SQLite + 真实 SQL 重建，LLM mock；live bot smoke 待用户环境，见决策文档 D①-7）
