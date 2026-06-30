## MODIFIED Requirements

### Requirement: KB per-tenant 文件分组于 kb/ 子目录

per-tenant 的 KB 关系库与向量库 SHALL 归组于 `tenants/<tenant>/kb/data/` 子目录(`kb/data/kb.db`、`kb/data/kb_vectors.db`,连同 SQLite 的 `-wal`/`-shm`),而非松散置于租户根或 `kb/` 根。`kb/` 根 SHALL 只承载 standalone KB 服务的配置面(`kb-service.yaml`、`.env`),`kb/data/` 承载数据/读面,二者分层与 agent home 同构。该 `kb/data/` 目录 SHALL 可作为**单一单元**被搬迁或挂载;容器部署下 node SHALL 把整个 `kb/data/` 目录(而非整个 `kb/`、亦非单个文件)以只读挂入 agent 容器,使 `-wal`/`-shm` 一并可见、agent 读到一致快照,同时把 `kb/` 根的 `.env`(KB embedding / connector secret)挡在 agent 读面之外。

#### Scenario: KB 文件位于 kb/data/ 子目录
- **WHEN** 解析某租户的 KB 关系库与向量库
- **THEN** 物理文件位于 `tenants/<tenant>/kb/data/kb.db` 与 `tenants/<tenant>/kb/data/kb_vectors.db`
- **AND** 租户根与 `kb/` 根都不直接含 `kb.db` / `kb_vectors.db`

#### Scenario: node 只读挂载 kb/data/ 维持 WAL 一致并隔离 secret
- **WHEN** node 容器为 agent 提供 KB 只读访问
- **THEN** node 只读挂载整个 `tenants/<tenant>/kb/data/` 目录(含 `-wal`/`-shm`),而非整个 `kb/`、亦非单个 `kb.db` 文件
- **AND** agent 读到的 KB 快照不滞后于已提交写入
- **AND** `kb/` 根的 `kb-service.yaml` / `.env` 不出现在 agent 容器的挂载读面内
