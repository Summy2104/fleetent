## MODIFIED Requirements

### Requirement: Per-tenant scoping bound at boot

服务 SHALL 默认为**单机多租户**:启动读本机服务级 config(不绑单一 `tenant_id`),按**每请求的 `principal.tenant_id`** 经 `tenant_scope(principal.tenant_id)` 解析该租户的 `kb_db` 与 `kb_vector_backend`(`TenantRouter` 缓存,廉价),只作用于 `tenants/<principal.tenant_id>/kb/data/`——请求间物理隔离,一个请求够不到别的租户库。服务 MAY 经 `--tenant <id>` 锁**单租户**(强隔离/调试):锁定时只受理该租户 principal,其它租户 principal 被拒(即旧的单租户行为)。

#### Scenario: 多租户按 principal 路由
- **WHEN** 服务默认(未锁 `--tenant`)启动,收到 `principal.tenant_id=T` 的请求
- **THEN** 经 `tenant_scope(T)` 解析并只作用于 `tenants/T/kb/data/`;同一进程可依次服务不同租户的请求,各自隔离
- **AND** 不存在"启动绑定单一租户"的硬 pin

#### Scenario: --tenant 锁单租户
- **WHEN** 服务以 `--tenant T` 启动,收到 `principal.tenant_id=T'`(T'≠T)的请求
- **THEN** 服务拒绝该请求(锁定模式回到单租户隔离语义)

### Requirement: Service authentication

服务 SHALL 用**本机共享 Bearer service key** 鉴权(传输层),并经 `X-Fleetent-Principal`(`identity.decode_ingress_principal`)解析请求主体;`principal.tenant_id` 为**路由/授权键**(决定作用于哪个租户 KB)。缺失或非法鉴权(无 service key / principal 不可解析)SHALL 被拒绝。service key 为本机服务级(落本机 config),不再 per-tenant。

#### Scenario: Valid service key and principal pass
- **WHEN** 请求带合法本机 Bearer service key 与可解析的 `X-Fleetent-Principal`
- **THEN** 服务受理并按 `principal.tenant_id` 路由到对应租户 KB 处理

#### Scenario: Missing auth is rejected
- **WHEN** 请求缺 Bearer key 或 `X-Fleetent-Principal` 不可解析
- **THEN** 服务拒绝该请求
