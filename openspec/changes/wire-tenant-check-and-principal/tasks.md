## 1. Edge 跨主体访问校验（/chat、/ws）

- [x] 1.1 写测试（integration）：请求者 `Principal.tenant_id=T1` 访问归属 `T2` 的 agent，经 `/chat` 与 `/ws` 都被拒（不运行、不触达 T2 数据） —— 见红
- [x] 1.2 写测试（integration）：同主体（双方 `default`）经 `/chat`、`/ws` 正常运行（校验放行，现状无感） —— 见红
- [x] 1.3 在 `runtime/agent_app.py` 的 `/chat`、`/ws` handler 解析 Principal 后、进入 `run`/`run_stream` 前调用 `_check_tenant(principal, agent_tenant)`，不符 default-closed 拒（HTTP 403 / WS close） —— 见绿

## 2. sub-agent / invoke_agent 继承 Principal（达成 identity-port「继承」）

- [x] 2.1 写测试（integration）：父运行主体为 `T1` 时派生 sub-agent，其 `Principal.tenant_id` 为 `T1`（非写死 `default`） —— 见红
- [x] 2.2 删除 `runtime/loop.py:676` 附近 `parent_principal=Principal(user_id=user_id, tenant_id="default")` 的写死，改为继承父/会话 Principal 的完整字段 —— 见绿
- [x] 2.3 写测试（integration）：`invoke_agent` 在回合内调起另一 agent，被调 run 收到当前回合 Principal（含 tenant_id） —— 见红
- [x] 2.4 在 `tools/builtin_tools.py` 的 `invoke_agent` 把 `tool_context.principal` 透传给 `agent_loop.run(...)` —— 见绿

## 3. TUI 全程携带 Principal

- [x] 3.1 写测试（integration）：TUI 经 bearer 建连后 `run_stream` 收到非空 `Principal`（含 tenant_id），而非裸 `user_id` —— 见红
- [x] 3.2 `tui/dispatch.py`：`Connection` 增加 `principal: Principal` 字段；建连处（`agent_app`）用已解析的 `tui_principal` 填充；`_stream_run` 把 `conn.principal` 传给 `run_stream` —— 见绿

## 4. 收尾

- [x] 4.1 `grep -rn "_check_tenant" src`：确认其在 `/chat`、`/ws` 均有调用点（不再零调用）
- [x] 4.2 `grep -rn "tenant_id=\"default\"" src/fleetent/runtime/loop.py`：sub-agent 无条件写死已移除（仅余 `principal is None` 的 standalone 兜底，符 D4）
- [x] 4.3 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
