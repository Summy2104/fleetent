## Why

`kb-standalone-ingest` 落地后 KB 已能自包含 ingest(配置文件 + 本地队列 + worker + standalone_sweep)。平台托管那套 KB ingest 控制面(`kb_connectors` 表 + sweep cron + management.db 队列 + admin 连接器/导入端点)现在是**冗余的第二套**,留着会长期双轨漂移、增加理解成本。本 change(②b 第二刀,scope A 全退)退役平台侧 KB ingest,收敛到**单一模型**:KB 服务自有 ingest,platform 零 KB ingest、变可选管理层。

孤儿检查(已做)确认:`agent_kbs` 绑定与 ingest **零关联**(纯读作用域,materialize + long_term_ctx 消费)——**绝不动**;退役表间无外键级联。

## What Changes

**🔴 退役(平台托管 KB ingest 控制面):**
- `kb_connector_store.py`、`kb_connector_sweep.py` 整文件删;server.py 摘 `__kb_connector_sync_sweep__` cron 注册;config 的 `kb_connector_sweep_interval_seconds` 删。
- `kb_admin_api` 删:7 个连接器端点(list/add/edit/delete/check/status/sync)、`POST /{kb_id}/documents`(import)、`/{kb_id}/sync`(sync-directory)、显式 `extract-entities` 端点,及其 `_enqueue_*_job` / `_wait_for_kb_ingest_job` / `_connector_settings` 等辅助。
- 管理库表:**drop `kb_connectors`**(迁移 051/052/101 的对应 down)、**drop `kb_ingest_jobs` + `kb_connector_schedule_state`**(迁移 099)——平台不再用管理库队列;新增前向 Alembic 迁移做 drop。
- `worker.py` 的 `run_job`:删 import_document / sync_directory / connector_sync 的**平台触发**接线;standalone 路径(本地队列、connector sync、extraction)保留。
- docker-compose:`kb-worker` 命令/接线调整为 standalone(本地队列)或随 KB 服务,不再 drain management.db。
- **删对应测试**(`test_kb_connector_admin.py`、`test_kb_connector_sweep.py`、`test_kb_admin_api` 的 import/sync 用例、`test_kb_worker` 的 management.db 队列用例)——它们测被退行为,删除是正确收尾,非回归。

**🟢 保留(与 ingest 无关):** `agent_kbs` + 4 个绑定端点;KB 定义 CRUD(list/create/edit/archive,写 kb.db);文档 list/preview/delete(读/写 kb.db);检索 playground / evaluations / observation;`long_term_ctx`、`materialize`、standalone ingest 全套。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `kb-connector-scheduler`: 平台 per-connector 周期调度(sweep + management.db 队列)**退役**——由 standalone KB 服务自有 sweep 取代(见 `kb-standalone-ingest`)。
- `kb-ingest-queue`: 持久 ingest 队列**从 management.db 退役**——队列归 KB 服务本地(standalone)。
- `kb-ingest-worker`: 平台启动的 kb-worker drain management.db 队列**退役**——worker 归 KB 服务、drain 本地队列。
- `kb-admin-api`: 删除文档 import / connector sync / 显式 extraction 触发等 ingest 端点;保留 KB 定义 / 文档 list-lifecycle / 检索 / observation / 绑定 / 权限审计端点。

## Impact

- **owning packages**:`fleetent.platform.knowledge_base_management`(删 store/sweep/连接器端点)、`fleetent.knowledge_base`(worker run_job 删平台触发分支)、`server.py`(摘 cron)、`migrations`(drop 表)、`docker-compose.yml`、`config.py`。
- **public API surface**:移除上述 admin 端点与平台连接器管理;standalone 配置(kb-service.yaml)成为唯一 KB ingest 配置入口。
- **owned tables**:drop `kb_connectors` / `kb_ingest_jobs` / `kb_connector_schedule_state`(管理库,前向 Alembic 迁移)。
- **铁律**:`agent_kbs` 表与绑定端点、`materialize._knowledge_for_agent`、`long_term_ctx` **零改动**。
- **cross-module 依赖**:退役后 management.db 不再有 KB ingest 表;standalone 路径不连 management.db(护栏保持)。
- **测试**:删被退行为的测试(非回归);保留/新增"退役后 standalone 仍跑 ingest + 绑定/读链路不受影响"的验证。
- **数据**:存量 management.db 的这几张表被 drop(数据是平台托管连接器配置/队列,退役语义即丢弃;连接器配置改由 kb-service.yaml 手动维护)。
