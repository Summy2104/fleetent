## Why

per-tenant 的 KB 数据文件(`kb.db`、`kb_vectors.db`)当前**松散躺在租户根** `tenants/<tenant_id>/`,和 `agents/` 子树平级、没有自己的边界。这带来两个问题:

1. **没有清晰的 KB 数据归属边界**——KB 数据无法作为一个自包含单元单独备份、挪进数据安全区、或将来交给独立 KB 服务接管。
2. **WAL ro 挂载隐患(cluster A2)**:node 容器把 `kb.db` / `kb_vectors.db` 作为**单个文件** RO 挂进 agent 容器(不含 `-wal/-shm`),agent 可能读到滞后快照。

把 KB 文件收进 per-tenant 的 `kb/` 子目录,一步同时解决这两点,且**为将来 KB 独立成服务铺好交接面**(服务直接接管 `tenants/<t>/kb/` 子树)——是与服务化决策无关的无悔卫生动作。

## What Changes

- **KB per-tenant 文件收进 `kb/` 子目录**:`tenants/<tenant_id>/kb.db` → `tenants/<tenant_id>/kb/kb.db`;`tenants/<tenant_id>/kb_vectors.db` → `tenants/<tenant_id>/kb/kb_vectors.db`(连同 `-wal`/`-shm`)。之后 `tenants/<t>/` 下只有两个边界清晰的子目录:`kb/`(KB 数据)与 `agents/`(各 agent 的家)。
- **node 容器改挂 `kb/` 整目录**:RO 挂载从"两个文件"变为"整个 `kb/` 目录"(含 `-wal`/`-shm`)→ agent 读到一致快照,消除 WAL 滞后隐患。
- **存量过渡**:解析/建库时,若发现 legacy 扁平 `tenants/<t>/kb.db` 且 `kb/` 尚不存在,则**幂等迁移**(把 `kb.db`/`-wal`/`-shm`/`kb_vectors.db` 移入 `kb/`),不破坏已部署环境。

不改变:KB 表结构、`tenant_id`/`kb_id` 列、路由 public 接口(`tenant_scope` / `agent_scope` 调用点不变);agent per-agent 库布局(`tenants/<t>/agents/<a>/data/...` 不动);management.db(平台)与其 KB 元数据表(`kb_connectors`/`agent_kbs`/`kb_ingest_jobs`)位置不动。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `tenant-scoped-db-routing`: per-tenant KB 关系库与向量库的物理路径由 `<tenant>/kb.db` / `<tenant>/kb_vectors.db` 改为 `<tenant>/kb/kb.db` / `<tenant>/kb/kb_vectors.db`;主体目录 provisioning 含 `<tenant>/kb/`;新增"KB 文件分组于 per-tenant `kb/` 子目录、可作为单元整目录挂载(WAL 一致)、legacy 扁平布局幂等迁移"的要求。

## Impact

- **owning package**:`fleetent`(`paths.py` 加 `tenant_kb_dir`)+ `fleetent.tenant_router`(`SQLiteTenantBackend.resolve` 路径)+ `fleetent.node`(`backend.py` 挂载 + `_prepare_tenant_kb`)+ `runtime.agent_app`(`_init_agent_db_schema` 若直接拼路径)。
- **public API surface**:路由解析器 `tenant_scope`/`agent_scope` 签名与调用点不变(调用方只表达作用域,不拼物理路径——本就如此);新增 `paths.tenant_kb_dir(tenant_id)` helper。
- **owned tables**:无表结构变更;仅物理文件位置变更,KB 嵌入式迁移内容不变。
- **config namespace**:无。
- **cross-module 依赖**:无新增;路由仍是 KB / agent 库的唯一物理路径来源(护栏不破)。
- **存量数据**:已部署环境的扁平 `kb.db`/`kb_vectors.db` 经幂等迁移移入 `kb/`;不破坏"agent 无 platform 单跑"基线。
- **测试**:integration(解析路由到 `<tenant>/kb/...`;legacy 扁平→迁移入 `kb/`;node 挂 `kb/` 目录;多租户物理隔离仍成立),`tmp_path` 隔离,绝不碰 `data/`。
