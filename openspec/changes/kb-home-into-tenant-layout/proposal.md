## Why

standalone KB 服务当前自己开了一棵 `<FLEETENT_HOME>/kb-service/<tenant>/` home(配置 + `data/`),而 agent 运行时读的是 tenant-first 布局的 `tenants/<tenant>/kb/`。两者在单机部署下指向**不同的物理文件**:KB 服务灌进去的库,不是 agent 实际读的库。这个分叉从租户足迹里岔出去,既割裂数据又多一套布局心智。把 KB service home 收进 `tenants/<tenant>/kb/`,让 service 写的就是 agent 读的同一份,消除割裂。

## What Changes

- **standalone KB service home 从 `<FLEETENT_HOME>/kb-service/<tenant>/` 迁入 `<FLEETENT_HOME>/tenants/<tenant>/kb/`**。`kb-service.yaml` 与 `.env` 落 `kb/` 根(运维/secret 面);`kb.db` / `kb_vectors.db` / `kb_ingest_queue.db` 落 `kb/data/`(数据/读面)。布局与 agent home(`agents/<id>/agent.yaml` + `.env` + `data/`)同构。
- **真正合一**:KB 服务写入的 `kb/data/kb.db` 与 agent retrieval 读取的库是**同一物理文件**,不再各持一份。
- **BREAKING(内部路径契约)** agent-read KB 文件从 `tenants/<tenant>/kb/kb.db` 下沉到 `tenants/<tenant>/kb/data/kb.db`(`kb_vectors.db` 同)。`tenant_router` 与 KB read service 的读点随之改。
- **BREAKING(node 挂载面收窄)** 容器化部署下 node 从"整目录 RO 挂 `tenants/<tenant>/kb/`"改为"只 RO 挂 `tenants/<tenant>/kb/data/`"。`.env`(KB embedding / connector secret)留在未被挂载的 `kb/` 根,**杜绝 secret 经 RO 挂载泄漏进 agent 容器**;`-wal`/`-shm` 与 `kb.db` 同在 `data/`,整挂 `data/` 仍带得上,一致快照不回归。
- **删除 `kb-worker` 的 legacy `load_config()` 兜底**(`worker.py` 读 tenant-less 的 `$FLEETENT_HOME/kb-service/.env`)。迁移后该路径指向不存在的位置;canonical 入口是 per-tenant `--config tenants/<tenant>/kb/kb-service.yaml`。
- **不变(刻意保留)**:配置文件名 `kb-service.yaml` / 模板 `kb-service.yaml.example`、CLI 命令 `fleetent kb-service init-config` / `kb-serve` / `kb-worker`、provider id `provider="kb-service"` 与 agent 名 `kb-service-standalone`——这些命名的是"KB 服务"这个东西,不是被废弃的 `kb-service/` 目录。
- **无存量迁移 shim**:KB 尚未接通真实数据,greenfield 改路径约定即可。

## Capabilities

### New Capabilities
<!-- 无新增 capability;本变更收口既有布局契约 -->

### Modified Capabilities
- `kb-standalone-ingest`: service home 从 `kb-service/<tenant>/` 迁至 `tenants/<tenant>/kb/`;反转"`data/` 内 SHALL NOT 出现 `tenants/`/`kb/` 中间层"为"配置在 `kb/` 根、数据在 `kb/data/`";`init-config` 脚手架目标路径随之改。
- `tenant-scoped-db-routing`: per-tenant KB 物理文件从 `tenants/<tenant>/kb/kb.db` 下沉至 `tenants/<tenant>/kb/data/kb.db`(向量同);node 容器挂载从"整个 `kb/`"收窄为"`kb/data/`"。
- `kb-read-service`: 只读读点从 `tenants/<tenant>/kb/` 改为 `tenants/<tenant>/kb/data/`。
- `kb-ingest-worker`: 删除 tenant-less legacy env 兜底(worker 只经 `--config` 加载);config 锚点路径更新为 `tenants/<tenant>/kb/`。

## Impact

- **代码**:`knowledge_base/service_init_config.py`(home 路径 + 显示串)、`knowledge_base/worker.py`(删 legacy `load_config()` 兜底)、`knowledge_base/service_config.py` 与模板(`data.home` 默认 `./data` 不变)、`paths.py`(新增 `tenant_kb_data_dir`)、`tenant_router.py`(`ensure_tenant_kb_dir` 指 `kb/data`)、`node/backend.py`(RO 挂载点 + `_prepare_tenant_kb` 指 `kb/data`)。
- **构建/部署**:`Makefile`(kb-serve / kb-worker / init-config 路径)、`docs/deployment/compose.md`。
- **文档**:`docs/architecture/agent-home-layout.md`(已落地约束 5/6 + 目标布局)、`docs/architecture/data-model.md`、`docs/operations/pilot-runbook.md`、`docs/operations/pilot-install-checklist.md`、`docs/operations/local-managed-stack.md`、`docs/capabilities/knowledge-base.md`、`docs/capabilities/config-management.md`。
- **测试**:`tests/unit/test_kb_service_init_config.py`、`test_knowledge_service_config.py`、`test_kb_worker_config.py`、`test_agent_home_materialize.py`、`test_makefile_deploy_targets.py`、`tests/integration/test_kb_standalone_service.py`、`test_packaged_config_templates.py`、`test_deployment_docs.py`、`tests/e2e/_kb_helpers.py` 及 node 挂载相关用例。
- **不触碰**:platform 托管 ingest(已退役)、KB 检索/分块/connector 逻辑、management.db schema。
