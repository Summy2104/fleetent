## Why

`slim-admin-cli` 计划删除 18 条已有 HTTP API 覆盖的冗余命令。审查发现其中 **6 条的删除前提不成立**——对应的平台 HTTP API 要么是空桩、要么完全不存在。删了就是丢功能而非删冗余。本 change 补齐这 4 块缺失的 API，使全部 18 条命令真正可安全退役，是 `slim-admin-cli` 的**前置依赖**。

> 审查依据（已核实代码）：
> - `agent_statistics/stats_admin_api.py` 的 `fetch_traces()`/`fetch_approvals()`/`pricing_table()` 全是 `return []`/`return None` 占位桩，`/admin/stats/*` 当前基于空 trace 集。
> - HTTP 无 `rotate-key`（按 user 原子轮换）端点；`POST /admin/users` 走 `create_web_user`（web 用户、不发 key），无法替代 CLI `create-user`（`create_user(name)` 建用户即发 `ma-` key）。
> - HTTP 无任何设置/清除 default agent 的端点。

## What Changes

- **观测查询 HTTP API**：新增 `/admin/observability/traces`、`/admin/observability/usage`、`/admin/observability/performance` 三个查询端点，直接包装 CLI 同款的 `observability.query_trace_events` / `get_usage_summary` / `get_performance_summary` 公共 API，**保留 CLI 的全部过滤维度**（run_id / user_id / agent / session / tenant / event_type / 时间窗 / limit）。同时把 `stats_admin_api.py` 的 `fetch_traces`/`fetch_approvals`/`pricing_table` 占位桩接到真实 observability 数据源（消除空壳 dashboard）。
- **服务账号创建 HTTP API**：新增 `POST /admin/service-principals`，包装 `user_store.create_user(name)`，建用户即签发 `ma-` API key，响应**一次性**返回明文 key——等价于 CLI `create-user` 的 bootstrap 路径。
- **API key 轮换 HTTP API**：新增 `POST /admin/users/{user_id}/rotate-key`，包装 `user_store.rotate_key(user_id)`（撤销该用户全部 active key + 发新 key，一次性返回明文）——等价于 CLI `rotate-key`。
- **default agent 控制面化**：把 default-agent 从"CLI 直编 agent.yaml 文件索引"改为**控制面属性**。新增 `PUT /admin/agents/{name}/default`（设为默认）和 `DELETE /admin/agents/default`（清除），default 标记由 materialize 路径下发为 agent.yaml 的 `bindings.default`——等价于 CLI `set-default-agent`，且与"控制面是配置真相源、node 只接收 materialize 产物"的目标架构一致。

## Capabilities

### New Capabilities

- `observability-admin-api`：平台 HTTP API，提供多维 trace 查询、usage 聚合、performance 指标查询。

### Modified Capabilities

- `agent-stats-aggregation`：`/admin/stats/*` 的数据源占位桩接真实 observability，不再返回空集。
- `api-key-management`：新增服务账号创建（建用户即发 key）与按 user 原子轮换 key 的 HTTP 端点。
- `default-agent`：default-agent 由文件索引编辑改为控制面属性 + materialize 下发；新增 HTTP 设置/清除端点。

## Impact

**owning package**：`platform`（`agent_statistics/`、`user_management/`、`agent_management_console/`、新增 `observability_management/`）+ `agent_lifecycle/materialize`（default 标记下发）

**public API surface（新增）**：
- `GET /admin/observability/traces`（多维过滤）
- `GET /admin/observability/usage`
- `GET /admin/observability/performance`
- `POST /admin/service-principals`（返回一次性 key）
- `POST /admin/users/{user_id}/rotate-key`（返回一次性 key）
- `PUT /admin/agents/{name}/default`
- `DELETE /admin/agents/default`

**owned tables**：无新表（observability traces 已存在；default 标记落 agent_admin_state 或 agent def，design 决定）

**config namespace**：无

**cross-module dependencies**：platform → `fleetent.observability`（公共 API，允许的单向依赖）；materialize 路径读 default 标记写入 `bindings.default`

**migration / shim plan**：default-agent 从文件索引迁移到控制面属性需 design 给出兼容方案（存量 agent.yaml 的 `bindings.default` 如何回填/对齐）；若涉及 agent_admin_state 加列则需 Alembic 迁移
