## 1. lift DDL 进 per-agent MIGRATIONS

- [ ] 1.1 写失败测试：空 per-agent 库经 Y 迁移后含 `traces` + `reflection_reports` 表，结构等价于现 `traces.py`/`reflection.py` 的 `ensure_schema` 产出
- [ ] 1.2 实现：把两处 `ensure_schema` 的 DDL 原样 lift 进 per-agent 库 `MIGRATIONS`（接 3b-1 版本之后），跑绿 1.1

## 2. 连接走 agent_scope + 接线

- [ ] 2.1 写失败测试：traces / reflection 的连接来自 `agent_scope(...).state_db`；护栏断言二者无 `create_database`-into-global / `ensure_schema`-into-global 残留
- [ ] 2.2 实现：traces.py / reflection.py 连接改走 agent_scope；删自连接；`agent_app._init_agent_db_schema` 接线，跑绿 2.1
- [ ] 2.3 跑既有 traces / reflection 测试确认行为不变

## 3. 收尾

- [ ] 3.1 不得 import platform、无新增裸 sqlite3.connect、named params；依赖护栏
- [ ] 3.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate per-agent-traces-reflection-lib --strict`
