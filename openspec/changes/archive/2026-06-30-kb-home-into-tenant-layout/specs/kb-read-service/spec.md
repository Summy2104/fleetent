## MODIFIED Requirements

### Requirement: Per-tenant scoping bound at boot

服务 SHALL 是 per-tenant 进程:启动时绑定一个 `tenant_id`,经 `tenant_scope(tenant_id)` 注入 `kb_db` 与 `kb_vector_backend` 一次。服务 SHALL 只读该租户的 `tenants/<tenant>/kb/data/`,物理上够不到其它租户的库。

#### Scenario: Boot binds tenant scope once
- **WHEN** 服务以 `tenant_id=T` 启动
- **THEN** 经 `tenant_scope(T)` 注入 KB 关系库与向量后端,只读 `tenants/T/kb/data/`

#### Scenario: Mismatched tenant is rejected
- **WHEN** 请求的 `principal.tenant_id` 与服务绑定的租户不一致
- **THEN** 服务拒绝该请求(不跨租户检索)

### Requirement: Read service does not own ingest

本服务 SHALL 只读 `kb/data/`,SHALL NOT 改变现有 ingest(worker / 队列 / connector secret)。KB 数据由现有 ingest 写入,服务读取同主机的 `tenants/<tenant>/kb/data/`。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: Service is read-only over kb/data/
- **WHEN** 检视服务实现
- **THEN** 服务只读 `tenants/<tenant>/kb/data/` 下的库,不写入,也不改 ingest 队列/worker/connector secret
- **AND** 服务进程不 `import fleetent.platform.*`
