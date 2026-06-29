## Context

当前路径(已核实):
- `paths.tenant_dir(t)` = `base_dir()/tenants/<t>`;`management.db` 在 `base_dir()` 根(平台,已独立)。
- `tenant_router.SQLiteTenantBackend.resolve(t)`(~line 110)直接拼 `tenant_dir/'kb.db'`、`tenant_dir/'kb_vectors.db'`。
- `node/backend.py`:`_bind_mount(_tenant_dir(t)/'kb.db', read_only=True)` 与 `kb_vectors.db`(line 134/136);`_prepare_tenant_kb`(204-208)建 `tenant_dir/'kb.db'`、touch `kb_vectors.db`。
- agent per-agent 库在 `tenants/<t>/agents/<a>/data/`(不动)。

本 change 把 per-tenant KB 两个文件收进 `tenants/<t>/kb/`。承接 [[agent-home-layout-refactor]] 的 tenant-first 布局,是 KB 独立服务化(Slice ②)的数据交接面雏形,但**与服务化决策无关**——纯卫生 + 修 WAL(cluster A2)。

## Goals / Non-Goals

**Goals:**
- per-tenant `kb.db`/`kb_vectors.db`(含 wal/shm)收进 `tenants/<t>/kb/`。
- node 改挂 `kb/` 整目录,修 WAL ro 挂载滞后。
- 存量扁平布局幂等迁移入 `kb/`。

**Non-Goals:**
- 不动 agent per-agent 库布局、management.db 及其 KB 元数据表(kb_connectors/agent_kbs/kb_ingest_jobs)。
- 不改 KB 表结构 / 嵌入式迁移内容 / 路由 public 接口。
- 不建 KB 服务(Slice ②);只为它备好数据单元。

## Decisions

### 决策:新增 `paths.tenant_kb_dir(t)`,单一来源
- `tenant_kb_dir(t) = tenant_dir(t)/"kb"`。`tenant_router.resolve` 与 `node/backend.py` 都经它取目录,不各自拼字符串(沿项目"路径常量单一来源"纪律)。

### 决策:存量幂等迁移在"开库前"做,move 而非 copy
- 在 `resolve()` / `_prepare_tenant_kb` 建立连接**之前**:若 `kb/` 不存在且租户根存在 `kb.db`,则 `mkdir kb/` 并 `move` `kb.db`、`kb.db-wal`、`kb.db-shm`、`kb_vectors.db`(及其 wal/shm)入 `kb/`。move(非 copy)保证不双份、幂等(已迁移则 `kb/` 已在、跳过)。
- **为什么开库前**:移动打开中的 SQLite 文件危险;迁移必须在任何连接建立前完成。单写者/启动期执行降低竞态。
- **替代**:永久兼容双路径(优先 `kb/`,回落扁平)。否决——留两套路径是长期负担;一次性迁移收敛更干净。

### 决策:node 挂 `kb/` 整目录(RO),取代两个文件挂载
- `_bind_mount(tenant_kb_dir(t), read_only=True)` 一条,替代原 kb.db + kb_vectors.db 两条文件挂载。目录挂载天然含 `-wal`/`-shm` → 修 WAL 滞后(cluster A2)。`_prepare_tenant_kb` 先在宿主建好 `kb/` 与库再挂。

### 决策:agent 读仍 RO、写仍在宿主/写者侧
- 挂载维持 RO(agent 只读 KB 不变);写者(ingest worker)写宿主 `kb/`。本 change 不改读写边界,只改"挂文件→挂目录"。

## Risks / Trade-offs

- **[迁移竞态]** 多进程同时首次 resolve 触发迁移。**Mitigation**:迁移幂等 + move 原子性;`kb/` 存在即跳过;provisioning 本就由 node reconcile / init 单点驱动,降低并发首触。
- **[遗漏路径拼接点]** 某处仍直接拼旧 `tenant_dir/'kb.db'`。**Mitigation**:grep 全仓 `'kb.db'`/`"kb.db"`/`kb_vectors` 字面量,全导向 `tenant_kb_dir`;护栏/集成覆盖。
- **[ro 目录挂载语义差异]** 目录 RO 挂载在不同容器后端行为。**Mitigation**:沿用 `_bind_mount` 既有机制,仅把 path 从文件换成目录;live/integration 验证 agent 仍能读、且读到最新。
- **[基线回归]** 破坏"agent 无 platform 单跑"。**Mitigation**:standalone `agent run` 路径也经同一 `resolve`/迁移;集成覆盖无 platform 下解析到 `kb/` 并可读写。

## Migration Plan

- 代码改路径 + 开库前幂等迁移。新环境直接建 `kb/`;存量环境首次 resolve/prepare 时把扁平文件移入 `kb/`。
- 回滚:还原代码后,已迁入 `kb/` 的文件需手动移回租户根(或保留旧代码兼容)——故 merge 前在 live/integration 验证迁移正确。
- 文档:更新 `docs/architecture/agent-home-layout.md` 的目录树。

## Open Questions

- 无。布局收敛明确;队列/连接器/绑定的归属是 Slice ② 的事,不在本 change。
