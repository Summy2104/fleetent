## REMOVED Requirements

### Requirement: 单主体作用域先行
**Reason**: 3d 打开多主体 fan-out，前序"仅 default 单主体"的过渡限制至此解除。
**Migration**: `tenant_scope`/`agent_scope` 接受真实主体并路由到 `<tenant>/` 物理分区（见下方"多主体 fan-out"要求）；调用点不变（抽象在 3a 已就位）。

## ADDED Requirements

### Requirement: 多主体 fan-out 与主体来源

`tenant_scope(tenant)` / `agent_scope(tenant, agent_id)` SHALL 按**真实主体**路由到 `<tenant>/` 物理分区（不再固定 `default`）。物理路由的主体 SHALL 取自**运行 agent 的归属主体**（`AgentContextIdentity.tenant_id`，来自 agent 配置/materialize），而非请求者 `Principal`。不同主体的库 SHALL 物理分处不同目录，一个 agent 进程 MUST 够不到别主体的库。

#### Scenario: 按 agent 归属主体路由

- **WHEN** 主体 `T1` 的 agent 运行并请求其库
- **THEN** 路由解析到 `<T1>/...`，与 `T2` 的库物理分处不同目录

#### Scenario: 跨主体物理隔离

- **WHEN** `T1` 的 agent 进程尝试访问数据
- **THEN** 只触及 `<T1>/` 下的库，物理上够不到 `<T2>/` 的任何库

### Requirement: 主体目录 provisioning

系统 SHALL 在需要时建立 `<tenant>/` 与 `<tenant>/<agent_id>/` 目录结构（platform onboard 时建立，或 router 开库时幂等 lazy 建父目录），使多主体物理分区可用。

#### Scenario: 新主体目录就绪

- **WHEN** 新主体/agent 首次需要其库
- **THEN** 对应 `<tenant>/<agent_id>/` 目录存在或被幂等建立，库可正常开
