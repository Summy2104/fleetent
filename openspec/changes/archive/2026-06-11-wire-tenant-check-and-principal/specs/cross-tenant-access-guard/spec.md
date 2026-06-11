## ADDED Requirements

### Requirement: Edge 跨主体访问校验
agent 的 edge 入口（`/chat`、`/ws` 及等价 HTTP / WS 入口）在运行目标 agent 前 SHALL 校验请求者 `Principal.tenant_id` 与目标 agent 的归属主体（`agent_tenant`，取自 agent 配置，与 `tenant-scoped-db-routing` 同源）一致。不一致 SHALL **default-closed 拒绝**，不进入运行。该校验是物理数据隔离（按 agent 归属主体路由）之上的访问准入层——物理隔离保证"够不到别主体的库"，本校验保证"别主体的请求者不能驱动本主体的 agent"。

#### Scenario: 同主体放行
- **WHEN** 请求者 `Principal.tenant_id` 与目标 agent 归属主体相同（如单主体下双方均 `default`）
- **THEN** 校验通过，agent 正常运行

#### Scenario: 跨主体拒绝
- **WHEN** 请求者 `Principal.tenant_id` 为 `T1`，目标 agent 归属主体为 `T2`
- **THEN** edge 拒绝该请求，不运行 agent，不触达 `T2` 的任何数据

#### Scenario: 校验在所有 agent 运行入口生效
- **WHEN** 经 `/chat`（POST）或 `/ws`（WebSocket）触发 agent 运行
- **THEN** 两条入口都在运行前执行跨主体校验（不存在绕过校验直接运行的入口）

### Requirement: Edge 携带 Principal 至运行
agent 的 edge 入口 SHALL 把已解析的 `Principal` 全程携带至 agent run（`run` / `run_stream`），MUST NOT 在 edge 把身份降级为裸 `user_id`。这是跨主体校验得以执行、且运行期身份/主体不断链的前提——principal-less 的 `user_id` fallback 仅作为无身份兜底，MUST NOT 在已认证的 edge 路径上被命中。

#### Scenario: TUI 连接携带 Principal
- **WHEN** TUI 经 bearer 认证建立连接并发起 run
- **THEN** 连接对象持有解析出的 `Principal`，`run_stream` 收到该 `Principal` 而非仅 `user_id` 字符串

#### Scenario: 已认证 edge 不走 principal-less 路径
- **WHEN** 一个已认证请求进入 agent 运行
- **THEN** run 收到非空 `Principal`，不回退到 `user_id="default"` 兜底
