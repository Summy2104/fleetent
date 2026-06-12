## 1. fired run 注入 outbound_connectors

- [ ] 1.1 写测试（unit）：monkeypatch `fleetent.runtime.loop.run` 捕获 kwargs；构造 task + `_fire(task, connectors={"slack": <sentinel>})`（mock principal/session_mgr）→ 断言 `loop.run` 收到的 `outbound_connectors` == `{"slack": <sentinel>}` —— 现行传 None → 见红
- [ ] 1.2 `cron_scheduler._agent_run` 增 `connectors` 形参并转发 `outbound_connectors=connectors or {}`；`_fire` 调用处传入已持有的 `connectors` —— 见绿
- [ ] 1.3 回归测试（unit）：`connectors=None`（无 IM 场景）→ `loop.run` 收到 `{}`，不报错
- [ ] 1.4 该层窄命令复跑确认绿

## 2. 收尾

- [ ] 2.1 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [ ] 2.2 grep 自查：`_agent_run` 调用点均带 connectors；`run_now`/`_task_fire` 两路径无遗漏
