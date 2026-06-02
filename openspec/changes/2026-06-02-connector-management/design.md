# Design — Connector Management (Admin)

## 范围与边界

本 change **只设计 Admin 管理面**：可观察行为、配置入口、代解绑 / 手动重连等触发动作。运行语义不在本面：

- **OAuth consent / 凭证加密 / 自动 refresh / 注入 / 离职联动** → `connectors` 域（[connectors.md](../../../docs/capabilities/connectors.md)）。
- **MCP 连接 / 工具注册 `server__{tool}` / 故障降级 / 探活重连** → `mcp` 域（[mcp-client spec](../../specs/mcp-client/spec.md)）。
- **工具访问白名单（allowed_tools）** → `governance` / `agent_policy` 域。

本面只调上述域的**只读查询接口**与**触发动作接口**，不复制其状态机、不重定义状态名。

## 两类接入并存模型

后台「connector 管理」一屏覆盖两类、互不混淆的接入：

| 维度 | OAuth connector | MCP server |
|------|-----------------|------------|
| 粒度 | per-user 凭证（每个用户独立授权） | per-server 连接（全局共享，不按用户授权） |
| 状态对象 | `(user, connector)` 授权态 | `(server)` 连接态 |
| 状态来源 | connectors 域授权状态查询 | mcp 域连接状态查询 |
| admin 可做 | 配 connector / 看授权矩阵 / 代用户 revoke | 看 server 状态 / 看注册工具 / 手动重连 / 诊断 |
| admin 不可做 | **代用户首次 consent** | （无对应硬约束） |

UI 以两个分区呈现（参照 platform.md 的两张 mermaid），共用同一套权限守卫与脱敏序列化。

## OAuth connector 管理面

### connector 目录与配置

- 列出已声明的所有 OAuth connector，每个展示：`id`、`authorize_url` / `token_url`、`scopes`、`client_id`、`enabled`、已授权用户数、最近授权 / 刷新时间。
- admin 可新增 / 编辑一个 connector 配置（加新外部系统 = 加一个 connector，不改核心代码），保存即生效。
- 配置落 `connectors` 表（`id` / `display_name` / `oauth_config` JSON / `enabled` / `created_at`），**client_secret 不入此表**——走 env / 密钥注入（对齐 connectors 域数据模型注解；管理面也绝不接收 / 展示明文 secret）。
- 仅 OAuth 2.x：不支持 OAuth 的系统不在接入范围（来自 connectors 域硬约束），新增表单不提供非 OAuth 接入类型，本面不绕过。

### per-user 授权矩阵（状态委托 connectors）

- `(user, connector)` 矩阵，每格状态**完全对齐 connectors 域的返回值**，不在本面新造状态名：
  - **未授权**：connectors 查询返回 `NeedsConsent`（从未授权）。
  - **已授权**：返回有效 `Credential`，展示已授权 scope 列表。
  - **失效需重授**：返回 `NeedsConsent`（refresh token 过期，不可自动恢复）。
  - **凭证错误**：返回 `CredentialError`（refresh 网络失败，可重试）。
- 「未授权」与「失效需重授」在 connectors 域都体现为 `NeedsConsent`；本面靠 grant 是否曾存在（`granted_at` / `revoked_at` / 标记失效）区分文案，状态判定本身委托 connectors 查询，本面不重新计算 token 是否过期。
- 支持按 user 或按 connector 两视角切换（同一份矩阵数据的两种聚合）。

### 代用户 revoke（语义委托 connectors）

- admin 对某 `(user, connector)` 解绑：本面调 connectors 域 `revoke(user_id, connector_id)`，由 connectors 删 grant（软删 `revoked_at`）+ 调外部系统 revoke endpoint。本面**不直接动 `connector_grants` 表**，只触发 + 展示结果 + 写审计。
- 高危动作：解绑、批量离职联动撤销要求**二次确认**（对齐 platform.md 权限矩阵与 audit 语义）。
- 解绑后该用户下次用该工具回到 `NeedsConsent`（语义由 connectors 保证）。

### admin 不可代首次 consent（硬约束 + UI 提示）

- OAuth consent 必须用户本人浏览器跳转完成。本面**不提供任何代授权入口**：未授权格只展示「需用户本人浏览器 consent」提示，不渲染「代为授权」按钮，对应 API 也不存在代 consent 端点。
- 这是 connectors 域硬约束的 UI 落地，本面不绕过。

### 离职 / 禁用联动可视 + 凭证生命周期观测

- 离职联动：展示 user-center 禁用某用户时 connectors 自动撤销其全部 connector 凭证的结果（哪些 connector 被 revoke、成功 / 失败），便于审计离职处置是否干净。结果来自 connectors 域离职联动查询，本面只渲染。
- 生命周期观测：按 connector 展示 access token 自动刷新成功 / 失败率、refresh token 过期导致的重新授权次数，定位「为什么某 connector 老要重新授权」。指标来源由 connectors / observability 域提供，本面只聚合呈现。

## MCP server 管理面

### server 列表 + 连接状态（状态委托 mcp）

- 列出所有已配置 MCP server（stdio / HTTP transport），每个展示连接状态，状态名**对齐 mcp 域**：
  - **已连接**：握手成功，工具已注册。
  - **启动时降级屏蔽**：启动握手失败被降级，注册工具数 0，平台其余功能不受影响（mcp 域保证启动不阻断）。
  - **探活失败重连中**：处于指数退避重连。
  - **标记永久不可用**：重试耗尽后标记。
- 展示注册工具数、`server__{tool}` 命名空间清单、最近握手 / 探活时间。

### 注册工具命名空间可见

- 展开某 server 查看其注册工具列表（名称 / 描述 / 入参 schema 概要）。工具命名空间 `{server_id}__{tool_name}`（双下划线，来自 mcp-client spec），供 admin 配 Agent allowed_tools 时知道有哪些 `server__*` 工具可白名单。
- 白名单 / 访问控制本身归 governance / agent_policy，本面只让工具可见。

### 手动重连 + mcp doctor（降级不阻断，只呈现 + 触发）

- 提供「手动重连 / 重新握手」按钮：触发 mcp 域重新发起握手，写审计。连接失败 / 降级不阻断平台启动（mcp 域保证），本面只做状态呈现与手动触发。
- `mcp doctor` 诊断入口：触发 mcp 域诊断，把结论渲染为红 / 黄 / 绿清单，**敏感认证值（token / API key / URL 中的凭证）脱敏**。

## 敏感值脱敏（贯穿所有视图）

- **绝不明文回显**：`client_secret`、access token、refresh token、MCP server 认证 header / env 中的密钥。
- **脱敏在序列化层统一处理**：所有 `/admin/connectors/*`、`/admin/mcp/*` 响应经同一脱敏序列化器（如 `_mask(value)` → 保留前缀 + `***`，或整体 `***`），避免每个端点各自处理而漏脱敏；审计 `detail` JSON 同样脱敏后再落库。
- connector 配置即便存了 client_secret（本面不存，走 env），管理面读到也只输出脱敏占位；本面 API 不接收明文 secret 字段。

## 权限与审计

- 路由 `/admin/connectors/*`、`/admin/mcp/*`，仿 `user_admin_api.py`：登录会话解析 → `auth.has_role` / `auth.require_role` 守卫。
  - **viewer**：只读——浏览 connector 目录、授权状态矩阵、MCP server 连接状态、mcp doctor 诊断结论。
  - **admin / built_in_admin**：写——新增 / 编辑 connector 配置、代用户 revoke、MCP server 配置变更、手动重连 / 重新握手。
- 写操作一律 `audit_log.write_audit(actor, action, target_type, target_id, detail)`：配置增改、代用户解绑、手动重连。
- 高危动作（代用户解绑、批量离职联动撤销）要求二次确认；批量动作关联批次 ID。

## 测试隔离（遵循 CLAUDE.md）

- `connector_admin_api.py` 不 import `agent_loop`，用 FastAPI **TestClient** 单测路由（与 `user_admin_api.py` 同款，规避 PEP 695 的 3.12 依赖）。
- **mock connectors / mcp 状态查询**：本面只消费跨域只读接口与触发动作，测试 patch 这些接口返回构造的授权态 / 连接态，断言矩阵渲染、状态文案、脱敏；**不发真实 OAuth / MCP 请求**（用 `respx` 或 `unittest.mock`）。
- **脱敏断言**：构造含 client_secret / token 的输入，断言任何响应体与审计 `detail` 均不含明文。
- **代 consent 守卫**：断言未授权格无代授权入口、不存在代 consent 端点（场景 110）。
- 数据库 / 路径隔离：connector 配置 store 复用统一 DB fixture 或 `monkeypatch` `DB_PATH` 到 `tmp_path`；named params（`:x`），不新增 `?` 占位符；schema 走 Alembic，不在 store 里 `_init_db()` 建表。
- 权限守卫：构造 viewer / admin / 无 session 会话，断言读放行、写 403、无 session 401。
