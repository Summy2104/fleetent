## 1. 统一 per-agent MIGRATIONS（合并 3b-1 session 列表 + append traces/reflection）

- [ ] 1.1 写失败测试：① 空 `agent_state.db` 经**统一** per-agent MIGRATIONS 迁移后含 `sessions`(v1) + `traces`(v2) + `reflection_reports`(v3)，结构等价于各自 `ensure_schema` 产出；② **回归保护**：连续两次 open（含已建库）不报 `SchemaTooNewError`、不重建（验证单文件单 user_version 由统一列表正确推进）
- [ ] 1.2 实现：新建统一 per-agent 迁移模块（含 3b-1 `session/migrations.py` 的 v1 步并入，traces=v2、reflection=v3，DDL 原样 lift 不改 schema）；`agent_app._init_agent_db_schema` 改为对该统一列表**单次** `open_state_db(AGENT_STATE_MIGRATIONS)`（替掉 3b-1 的 `open_state_db(SESSION_MIGRATIONS)`），跑绿 1.1。**不得给 traces/reflection 各建独立列表跑同一文件**（user_version 撞戳）

## 2. 连接走 agent_scope + 接线

- [ ] 2.1 写失败测试：traces / reflection 的连接来自 `agent_scope(...).state_db`；护栏断言二者无 `create_database`-into-global / `ensure_schema`-into-global 残留
- [ ] 2.2 实现：traces.py / reflection.py 连接改走 agent_scope；删自连接；`agent_app._init_agent_db_schema` 接线，跑绿 2.1
- [ ] 2.3 跑既有 traces / reflection 测试确认行为不变

## 3. 收尾

- [ ] 3.1 不得 import platform、无新增裸 sqlite3.connect、named params；依赖护栏
- [ ] 3.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate per-agent-traces-reflection-lib --strict`
