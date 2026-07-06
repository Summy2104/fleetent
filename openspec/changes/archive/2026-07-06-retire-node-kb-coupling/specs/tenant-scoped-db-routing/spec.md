# tenant-scoped-db-routing — Delta

## MODIFIED Requirements

### Requirement: KB per-tenant 文件分组于 kb/ 子目录

per-tenant 的 KB 关系库与向量库 SHALL 归组于 `tenants/<tenant>/kb/data/` 子目录(`kb/data/kb.db`、`kb/data/kb_vectors.db`,连同 SQLite 的 `-wal`/`-shm`),而非松散置于租户根或 `kb/` 根。`kb/` 根 SHALL 只承载 standalone KB 服务的配置面(`kb-service.yaml`、`.env`),`kb/data/` 承载数据/读面,二者分层与 agent home 同构。该 `kb/data/` 目录 SHALL 可作为**单一单元**被搬迁。**agent 容器 SHALL NOT 挂载租户 KB 文件**——managed agent 的 KB 访问一律经中心 kb-serve HTTP(见 `agent-knowledge-config`),node MUST NOT 为 agent 容器准备或挂载任何 KB 数据面。

`ensure_tenant_kb_dir` 等 provision 路径 SHALL **仅幂等建立 `kb/data/` 目录**,SHALL NOT 自动搬迁任何 legacy 旧址布局(租户根扁平 `tenants/<tenant>/kb.db`、或 `kb/` 根旧址布局,即 `kb.db` / `kb_vectors.db` 直接位于 `kb/` 根)的数据——采 clean-break:存量旧址文件保持原地,如需保留由运维自行移入 `kb/data/` 或删除。

#### Scenario: KB 文件位于 kb/data/ 子目录
- **WHEN** 解析某租户的 KB 关系库与向量库
- **THEN** 物理文件位于 `tenants/<tenant>/kb/data/kb.db` 与 `tenants/<tenant>/kb/data/kb_vectors.db`
- **AND** 租户根与 `kb/` 根都不直接含 `kb.db` / `kb_vectors.db`

#### Scenario: agent 容器无任何 KB 挂载
- **WHEN** node 容器后端拉起一个 agent 容器
- **THEN** docker run 参数只挂载该 agent 的 home 卷,不含任何指向 `tenants/<tenant>/kb/` 的挂载
- **AND** node 在 spawn 前不初始化租户 KB 库（kb.db schema 与 kb_vectors.db 的建立归 KB 服务 migrate-on-open / router lazy-create）

#### Scenario: legacy 旧址不自动迁移
- **WHEN** 存量环境的 KB 文件位于 legacy 旧址(`tenants/<tenant>/kb.db` 租户根、或 `kb.db` / `kb_vectors.db` 直接位于 `tenants/<tenant>/kb/` 根)、而 `kb/data/` 不存在
- **THEN** provision 仅幂等建立空的 `kb/data/`,旧址文件保持原地、不被自动搬迁
