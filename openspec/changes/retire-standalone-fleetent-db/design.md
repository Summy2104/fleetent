## Context

standalone agent boot 现状（`runtime/agent_app.py`）：
- `_redirect_agent_data_paths()` 用 `os.environ.setdefault("DATABASE_URL", sqlite:///{data_dir}/fleetent.db)` 设锚。
- `_start_infra()` 读 `os.environ["DATABASE_URL"]`，非空才调 `_init_agent_db_schema(database_url, ...)`。
- `_init_agent_db_schema()` 内 `db = create_database(database_url)` → `schedule_store.ensure_schema(db)`（唯一用到这个 db 的地方），随后 `data_dir = db.path.parent` 派生 router，把 KB/shared/agent_state 路由出去并逐个 `set_state_db`/`set_database` 注入。

即 `fleetent.db` 现仅承载 `scheduled_tasks`（+ 当 data_dir 锚点 + 当 `Settings().database_url` 的隐式落点）。`scheduled_tasks` 已被 alembic 071 从管理库 drop、判为 agent 侧 per-agent 表，scheduler 由 agent 进程的 `CronScheduler` 触发（平台 managed 侧不碰）。`db.default_database()` 是 #3b 遗留的 backward-compat fallback，当前**零调用方**。

## Goals / Non-Goals

**Goals:**
- `scheduled_tasks` 与其它 agent 侧表同住 `agent_state.db`，schema 权威收口到统一嵌入式 Y。
- standalone agent 不再创建 `fleetent.db`，消除与 `management.db` 的命名混淆。
- `schedule_store` 改注入式，删 `ensure_schema` + `Settings().database_url` 自连接。
- 拆除 `default_database()` 这一未注入兜底（避免 standalone 误落 `management.db`）。

**Non-Goals:**
- 不改 scheduler 触发逻辑 / `schedule` 工具 / `cron_scheduler` 的依赖方向。
- 不动 managed 平台的维护 scheduler（playground 清理）。
- 不迁移既有 `fleetent.db` 数据（上线前无真实持久 cron）。
- 不动 KB / shared_memory 的路由（已落地）。

## Decisions

1. **`scheduled_tasks` 进 `AGENT_STATE_MIGRATIONS` 新增一版**：把 `schedule_store._TABLE_DDL` 原样 lift 成一条 `(ver, sql)`，列与索引不变（`agent_name` 仍不存在）。版本号取当前 `AGENT_STATE_MIGRATIONS` 末尾 +1（实现时以代码实际最大版本为准，不在 spec 钉死数字）。

2. **`schedule_store` 注入式**：新增模块级 `_state_db` + `set_state_db(db)`，`_database()` 返回注入句柄（未注入则 raise 明确错误，与 traces/reflection/memory 同款）；删 `ensure_schema()` 与 `_database()` 里的 `create_database(Settings().database_url)`。

3. **boot 锚点改 `data_dir`**：`_init_agent_db_schema` 签名从 `(database_url, ...)` 改 `(data_dir: Path, ...)`；内部 `router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))` 直接锚 `home_dir/data`，不再先建 `fleetent.db`；agent_state 注入后追加 `schedule_store.set_state_db(agent_state_db)`。`_start_infra()` 触发条件从"`DATABASE_URL` 非空"改为"传入的 `data_dir` 存在"。`_redirect_agent_data_paths()` 删掉设 `DATABASE_URL=fleetent.db` 那行。

4. **移除 `db.default_database()`**：零调用方，删除函数本体；保留 `create_database` / `Settings().database_url` 供 managed 平台 store 显式使用（platform 侧不受影响，server.py 仍 `DATABASE_URL=management.db`）。

5. **不留 shim**：`schedule_store.ensure_schema` 仅被 `agent_app` 内部调用（已确认无其它调用方），直接删，不留 re-export。

## Risks / Trade-offs

- **standalone 不再设 `DATABASE_URL` → 任何读 `Settings().database_url` 的代码在 standalone 会落到默认 `management.db`（不存在）**。缓解：standalone 路径已确认仅 `schedule_store` 读 `Settings().database_url`（本 change 改注入），其余读者（user_store/agent_store/platform stores）均为 managed 侧、standalone 不触达；`default_database()` 一并删除收窄面。任务含一条 grep 守卫 + 「无 platform、无 management.db」基线对话验证。
- **`cron_scheduler` 依赖 `schedule_store` 已注入**：`_start_scheduler` 在 `_init_agent_db_schema`（含 `set_state_db`）之后调用，顺序已满足；任务显式核对 boot 顺序。
- **forward-only 历史**：`scheduled_tasks` 的 lift 只新增版本、不改旧版本；旧 `fleetent.db` 作孤儿，文档/部署说明交代清理（与 `budget_usage`、`session_anti_flap` 等历史孤儿同处理范式）。
- **测试分层**：schema/CRUD/boot 属真实 DB，须 integration（`tmp_path` + 统一 fixture）；纯 DDL ser/de 或路由分派可 unit。
