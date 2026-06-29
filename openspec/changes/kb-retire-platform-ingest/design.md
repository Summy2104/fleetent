## Context

孤儿检查(a909641c)已精确测绘平台侧 KB ingest 面。前置:`kb-standalone-ingest` 已落地(KB 自包含 ingest:本地队列 + worker + standalone_sweep + 配置文件)。scope A(用户已拍)= 平台零 KB ingest、全退。

关键交叉:`ingest/runtime.py:303` 的自动 extraction 入队经 `kb_ingest_jobs.enqueue_job`(队列连接已被 standalone 参数化)→ standalone 下入本地队列,不依赖 management.db。所以退役 management.db 队列后,extraction 经 standalone 本地队列继续工作。

**铁律**:`agent_kbs`(绑定/读作用域)与 `materialize._knowledge_for_agent` / `long_term_ctx` 零关联 ingest——**绝不动**(孤儿检查已验证零外键、纯读作用域)。

## Goals / Non-Goals

**Goals:**
- 删平台侧 KB ingest:连接器(store/sweep/端点/表)、文档 import/sync 端点、显式 extract 端点、management.db 队列、平台 kb-worker 接线。
- 收敛到单一模型:standalone KB 服务自有 ingest;platform 零 KB ingest。
- 删被退行为的测试;保留/加"退役后 standalone 仍跑 + 绑定/读链路不变"验证。

**Non-Goals:**
- 不动 `agent_kbs` / 绑定端点 / materialize / long_term_ctx。
- 不动 KB 定义 CRUD / 文档 list-lifecycle / 检索 / observation 端点。
- 不动 standalone ingest(已落地)、不动 knowledge_base 检索核。
- 不做 platform 作可选管理 UI(更后,可选)。

## Decisions

### 决策:全退,分组顺序退、每组验证
- 按"连接器 → 文档 import/sync → 队列+sweep+worker接线 → 表 drop"顺序退,每组退完跑测试确认 standalone ingest 仍绿、绑定/读链路不受影响。

### 决策:management.db 三表 drop 用前向 Alembic 迁移
- `kb_connectors`(051/052/101)、`kb_ingest_jobs` + `kb_connector_schedule_state`(099)→ 新增一条前向迁移 drop 这三张表(孤儿检查确认无外键级联)。迁移号取当前 head 下一个,**勿硬编码**(并行 change 可能占号),merge 后 `uv run alembic heads` 确认单 head。

### 决策:worker run_job 删平台触发分支,留 standalone 用的
- `worker.py run_job`:删 import_document / sync_directory / connector_sync 的**平台**触发接线;standalone 经本地队列用的 connector sync / extraction 分支保留(standalone 自有 sweep 入本地队列驱动)。

### 决策:被退测试删除,非"修复"
- `test_kb_connector_admin.py`、`test_kb_connector_sweep.py`、`test_kb_admin_api` 的 import/sync 用例、`test_kb_worker` 的 management.db 队列用例——**删除**(测的是被退行为);不要试图"修绿"。

### 决策:docker-compose kb-worker 调整为 standalone
- `kb-worker` 服务不再以 management.db 为 queue_database;改为随 KB 服务 / drain 本地队列(或并入 KB 服务进程组)。具体接线与 dockerize 协同;本 change 保证 compose 不再依赖 management.db 队列。

## Risks / Trade-offs

- **[漏引用破东西]** 平台侧 ingest 面广(kb_admin_api 大杂烩)。**Mitigation**:严格照孤儿检查清单;退每组后跑 module-boundaries + 全量 integration;`git grep` 残留符号(`kb_connector_store`/`kb_connector_sweep`/`enqueue_connector_job` 等)确认无悬空引用。
- **[误伤 agent_kbs / 读链路]** **Mitigation**:铁律——绑定端点/表/materialize/long_term_ctx 不在退役清单;加测试断言退役后 `by-agent`/`/{kb_id}/agents` 仍工作、long_term_ctx 仍能解析 kb_ids。
- **[extraction 断]** management.db 队列退役后 extraction 必须经 standalone 本地队列。**Mitigation**:测试断言退役后(standalone 配置下)ingest→自动 extraction→图谱写入仍成立。
- **[迁移撞号]** drop 迁移与并行 change。**Mitigation**:迁移号取 head 下一个、勿硬编码;merge 后 `alembic heads` 单 head 自检。
- **[存量数据丢弃]** drop 三表丢平台连接器配置/队列。**Mitigation**:语义即如此(连接器配置改 kb-service.yaml 手动维护);文档说明升级须把平台连接器配置誊到 kb-service.yaml。

## Migration Plan

- 前向 Alembic 迁移 drop 三表;代码删平台 ingest 件 + 端点 + cron + compose 接线;删被退测试。
- 升级:存量平台连接器配置(management.db `kb_connectors`)在升级前誊抄到 standalone `kb-service.yaml`(文档给步骤);drop 后平台不再管 KB 连接器。
- 回滚:还原代码 + 迁移 down 重建表(数据需另行恢复);故 merge 前全量验证。

## Open Questions

- docker-compose 的 kb-worker 是并入 KB 服务进程组还是独立 standalone worker:与 dockerize/#3 部署刀协同,实现时定。
