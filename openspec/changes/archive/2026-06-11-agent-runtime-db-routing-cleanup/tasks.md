## 1. 统一 MIGRATIONS 收编 4 张表

- [x] 1.1 写测试（integration）：以统一 `MIGRATIONS` 打开全新 `agent_state.db` 后，含 `session_anti_flap`、`sub_agent_runs`、`memory_maintenance_proposals`、`skill_proposals` 四表，且列集与原 `ensure_schema`/`init_*_db` DDL 一致 —— 见红
- [x] 1.2 把 4 张表的 `CREATE TABLE`（+ 原索引）原样 lift 进 `runtime/agent_state_migrations.py`，版本号取当前 max+1 起递增 append（不硬编码、不改列） —— 见绿

## 2. session_anti_flap / sub_agent_runs 改经 agent_scope + db.py

- [x] 2.1 写测试（integration）：platform 下两个 agent 各写压缩防抖 / 子 agent 记录，分别落各自 `agent_state.db`、互不可见、均不落管理库 —— 见红
- [x] 2.2 `runtime/context.py`：`session_anti_flap` 的 `_anti_flap_conn` / `init_anti_flap_db` 改经 per-agent state DB（`agent_scope` + `db.py`），删 `from user_store import DB_PATH` + 裸 `sqlite3.connect`；建表交统一 MIGRATIONS —— 见绿
- [x] 2.3 `runtime/sub_agent_lifecycle.py`：`sub_agent_runs` 的 `_conn` / `init_db` 同样改经 state DB、删裸连；建表交统一 MIGRATIONS —— 见绿
- [x] 2.4 grep 自查：`runtime/context.py`、`runtime/sub_agent_lifecycle.py` 不再含 `sqlite3.connect(DB_PATH)`

## 3. memory_maintenance_proposals / skill_proposals 去旁路

- [x] 3.1 写测试（integration）：`memory_maintenance_proposals` / `skill_proposals` 经统一迁移建立（移除独立 ensure_schema 后仍可读写） —— 见红
- [x] 3.2 `memory/proposal_store.py`：移除独立建表旁路，依赖统一 MIGRATIONS（store 经 `agent_scope` 注入连接） —— 见绿（核查无独立建表旁路：proposal_store 既经 `store.database()` 注入，schema 在 1.2 已并入统一 MIGRATIONS，无代码改动）
- [x] 3.3 写测试（integration）：`reflection` 未注入 `_state_db` 时不 fallback 管理库（不在 `Settings().database_url` 建/写 `skill_proposals`） —— 见红
- [x] 3.4 `reflection/reflection.py`：`_database()` 删管理库 fallback 分支；`skill_proposals` 建表交统一 MIGRATIONS —— 见绿

## 4. 验证基线与收尾

- [x] 4.1 写测试（integration）：无 platform、管理库表不存在下 `fleetent agent run` 可完成对话，4 张表落 agent 自己的 `agent_state.db`（agent/platform 解耦基线）
- [x] 4.2 同步 `docs/architecture/data-model.md` §3：移除 §3.2 ⚠️「错位」注与 §3.3 ⚠️「未进统一 MIGRATIONS」注，把这 4 张表正式列入 §3.3 per-agent，并补进 §3.3 明细图
- [x] 4.3 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
