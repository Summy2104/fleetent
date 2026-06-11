## 1. scheduled_tasks 并入 agent_state.db 嵌入式 Y

- [x] 1.1 写测试（integration）：以 `AGENT_STATE_MIGRATIONS` 打开全新 `agent_state.db` 后，`scheduled_tasks` 表存在且列齐全（含 `schedule_kind`/`origin`/`deliver`/`last_run_at`/`next_run_at` 等，`agent_name` 不存在）—— 见红
- [x] 1.2 在 `runtime/agent_state_migrations.py` 末尾新增一版 `(ver, sql)`，把 `schedule_store._TABLE_DDL` 原样 lift（列/索引/named-param 风格不变）—— 见绿
- [x] 1.3 该层窄命令复跑确认绿

## 2. schedule_store 改注入式（删 ensure_schema + Settings 自连接）

- [x] 2.1 写测试（integration）：`schedule_store.set_state_db(db)` 注入后，`create`/`list_tasks`/`delete` 走注入库；未注入时调用 CRUD 抛明确错误（与 traces/reflection 同款）—— 见红
- [x] 2.2 `schedule_store`：新增 `_state_db` + `set_state_db(db)`，`_database()` 返回注入句柄（未注入 raise）；删 `ensure_schema()` 与 `_database()` 里的 `create_database(Settings().database_url)` —— 见绿
- [x] 2.3 grep 自查：`schedule_store.py` 无 `Settings().database_url`、无 `ensure_schema`；全仓无 `schedule_store.ensure_schema` 调用残留

## 3. agent_app boot 改 data_dir 锚点、退役 fleetent.db

- [x] 3.1 写测试（integration）：`fleetent agent run` 走 `_start_infra()`（或其等价 boot helper）后，per-agent `agent_state.db` 含 `scheduled_tasks`，且 agent `data/` 下**不生成 `fleetent.db`** —— 见红
- [x] 3.2 `_init_agent_db_schema` 签名 `(database_url,...)`→`(data_dir: Path,...)`，内部 router 直接锚 `data_dir`、不再 `create_database(database_url)`/不再 `schedule_store.ensure_schema`；agent_state 注入后追加 `schedule_store.set_state_db(agent_state_db)` —— 见绿
- [x] 3.3 `_redirect_agent_data_paths()` 删除设 `DATABASE_URL=fleetent.db` 那行；`_start_infra()` schema 初始化触发改为「data_dir 存在即初始化」（不再读 `os.environ["DATABASE_URL"]`）
- [x] 3.4 核对 boot 顺序：`_start_scheduler`（`cron_scheduler`）在 `schedule_store.set_state_db` 之后执行

## 4. 移除死代码 default_database()

- [x] 4.1 grep 确认 `default_database()` 零调用方（仅定义处）
- [x] 4.2 删 `db.py` 的 `default_database()`；保留 `create_database` / `Settings().database_url`（managed 平台 store 仍显式使用）

## 5. 文档同步

- [x] 5.1 `data-model.md`：`scheduled_tasks` 从 §3.2 管理库（删 `users ||--o{ scheduled_tasks` 关系）移到 §3.3 per-agent 表清单（agent_state.db）；§1/末尾如有 `fleetent.db` 锚点描述一并修正
- [x] 5.2 修 `runtime/context.py:665` 注释：「per-agent `fleetent.db`」→「per-agent `agent_state.db`」

## 6. 收尾

- [x] 6.1 验证基线：「无 platform、无 `management.db`」环境下 `fleetent agent run` 对话成功（grep 守卫确认 standalone 路径无 `Settings().database_url` 读者）；scheduler 注册/触发正常
- [x] 6.2 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
