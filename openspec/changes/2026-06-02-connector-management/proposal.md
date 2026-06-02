## Why

平台已具备两类外部接入运行能力，但**缺一个统一的 Admin 管理面**让 admin 一屏看清「哪些外部系统接入了、谁授权了、连得通吗」：

1. **OAuth connector 不可观测**：[connectors](../../../docs/capabilities/connectors.md) 已实现 per-user OAuth consent、加密凭证存储、自动 refresh、`NeedsConsent` / `CredentialError` 区分、离职撤销，但 admin 无法在后台看 connector 目录、看 (user, connector) 授权矩阵、代用户解绑、审计离职联动是否干净。
2. **MCP server 不可观测**：[mcp](../../../docs/capabilities/mcp.md) 已实现 stdio / HTTP transport、启动时降级不阻断、工具 `server__{tool}` 注册、探活与指数退避重连，但 admin 看不到 server 列表与连接状态、看不到注册了哪些 `server__*` 工具、无法手动触发重连或 `mcp doctor` 诊断。
3. **凭证 / 工具配置纯靠改文件**：加一个新外部系统、调一个 MCP server 配置目前要改 `config/*.yaml`，admin 没有后台入口。

本 change **只叠加 Admin 管理面（可观察行为 + 配置入口 + 代解绑/手动重连触发）**，不重定义运行语义：OAuth consent / 凭证加密 / 自动 refresh / 注入 / 离职联动归 connectors 域，MCP 连接 / 工具注册 / 故障降级归 mcp 域，工具访问白名单归 governance 域，本面只交叉引用。

## What Changes

**ADDED**
- `oauth-connector-admin`：connector 目录与配置（id / authorize·token endpoint / scopes / client_id，client_secret 等敏感值脱敏；admin 可新增·编辑一个 connector 配置 = 加新外部系统不改核心代码）；per-user (user, connector) 授权矩阵（未授权 / 已授权含 scopes / 失效需重授 / 凭证错误，对齐 connectors 的 `NeedsConsent` / `CredentialError`，可按 user 或按 connector 两视角切换）；代用户 revoke（删凭证 + 调外部 revoke endpoint，语义委托 connectors，二次确认 + 写审计）；离职 / 禁用联动可视（展示 user-center 禁用用户时 connectors 自动撤销结果）；凭证生命周期观测（refresh 成功 / 失败率、重新授权次数）；**admin 不能代用户完成首次 consent** 的硬约束（UI 不提供代授权入口，明确提示本人浏览器跳转）。
- `mcp-server-admin`：MCP server 列表 + 连接状态（已连接 / 启动时降级屏蔽 / 探活失败重连中 / 标记永久不可用，对齐 mcp 降级与健康语义）；注册工具命名空间 `server__{tool}` 可见（名称 / 描述 / 入参 schema 概要，供配 Agent allowed_tools 参考）；手动重连 / 重新握手；`mcp doctor` 诊断入口（红 / 黄 / 绿清单，认证值脱敏）；权限与审计（配置增改 / 手动重连写审计，仅 admin 可操作）。

**MODIFIED**
- 无核心运行模块语义变更。仅新增管理面读写与配置表（见 Impact）。

## Capabilities

### New Capabilities

- `oauth-connector-admin`
- `mcp-server-admin`

### Modified Capabilities

- 无（运行语义复用 `connectors` / `mcp-client` / `governance`，本 change 不修改其 spec）

## Impact

- **代码**：
  - 新增：`connector_admin_api.py`（`/admin/connectors/*`、`/admin/mcp/*` 路由，仿 `user_admin_api.py`，复用 `auth.require_role` / `auth.has_role` + `audit_log.write_audit`，不 import `agent_loop` 以便 TestClient 隔离测试）。
  - 新增（按 0.x 决策）：connector 配置 store（`connector_config_store.py`，落 `connectors` 配置表）。MCP server 配置当前来自 `config/mcp.yaml`，管理面读其当前配置与运行态；是否落库由 0.x 决策。
  - 修改：`server.py`（mount `connector_admin_api.router`）。
- **跨域 follow-up（运行语义在各域，本面只消费其只读接口 + 触发动作）**：
  - **connectors 域**需暴露：授权状态查询（返回 `(user, connector) → 未授权 / 已授权 + scopes / NeedsConsent / CredentialError`）+ 代用户 `revoke(user_id, connector_id)` + 离职联动撤销结果查询。connectors 已声明「授权状态查询」「离职 / 禁用联动」「主动解绑 revoke」能力，本面消费之。
  - **mcp 域**需暴露：server 连接状态查询（含降级 / 重连中 / 永久不可用）+ 注册工具清单（`server__{tool}` + schema 概要）+ 手动重连 / 重新握手触发 + `mcp doctor` 诊断结果。
  - **governance 域**消费 `server__*` 工具清单做 allowed_tools 白名单（本面只让工具可见，不做访问控制）。
- **数据**：新增 `connectors` 配置表（`id` / `display_name` / `oauth_config`(JSON: authorize_url / token_url / scopes / client_id) / `enabled` / `created_at`，**client_secret 不入表，走 env / 密钥注入**，对齐 connectors 域数据模型注解）。新表走 Alembic（是否需要由 0.x 决策——若 connectors 域已建该表则本面只读复用，不重复建）。所有写审计落既有 `audit_log` 表。
- **安全 / 破坏性**：任何视图与日志均不明文回显 client_secret / access token / refresh token（脱敏在序列化层统一处理）。无破坏性变更；纯增量管理面。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(connector_config_store): connectors config table + masked serialization`（按 0.x 决策，1.x）
2. `feat(connector_admin_api): /admin/connectors directory + config CRUD (masked)`（2.x）
3. `feat(connector_admin_api): per-user grant matrix + no-consent guard`（3.x）
4. `feat(connector_admin_api): admin revoke + offboarding linkage view + lifecycle metrics`（4.x）
5. `feat(connector_admin_api): /admin/mcp server list + connection status + namespace`（5.x）
6. `feat(connector_admin_api): manual reconnect + mcp doctor diagnostic entry (masked)`（6.x）
7. `feat(server): mount connector_admin_api router`（7.x）
