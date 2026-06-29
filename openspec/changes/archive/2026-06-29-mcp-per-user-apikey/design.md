## Context

`mcp-per-user-oauth2`（切片 1/2，已并 main）建立了 per-user 凭据的全套基础设施：`(user_id, agent_id, server_id)` 三元组隔离、注入缝 `set_user_token_resolver` + 统一 `resolve_user_token`、per-request 注入（`_PerUserBearerAuth` http / stdio env）、无-token degrade 触发、DM 授权链接投递（`set_authorization_link_deliverer` / directed-reach）、管理库 `mcp_user_tokens` + node loopback 通道 + platform 端点（OAuth 的 pending/callback/token）、中立 `fleetent.mcp_auth_models` 鉴权 schema。

当前 api-key 鉴权是 **per-server 静态**：`auth_type=api_key` + `key_env` → `os.environ[key_env]` → 烘焙进会话头 `Authorization: Bearer`（`client.py`）。全用户共享一把机器 key，无 per-user 路径。

约束（沿用 OAuth 切片）：agent runtime 禁止 import platform；无 platform 时 standalone 照跑；明文 key 密文落库、不出对话、managed 不出 platform；长生命周期异步资源 owner-task 同 task；手写 SQL 走 store 边界。

## Goals / Non-Goals

**Goals:**
- per-user 动态 api-key/bearer：用户提供自己已有的明文 key，按三元组隔离存储 + per-request 注入。
- 两种提交方式 per-server 可配，默认安全表单（模式 1）：DM 一次性链接 → fleetent 自托管表单 → 提交存库，**零平台登录**；可选对话内工具（模式 2，限 DM）。
- 最大化复用 OAuth 切片基础设施；standalone 与 managed 两态并存；静态 api_key 行为不变。

**Non-Goals:**
- refresh（api-key 不刷新，吊销则重交）、撤销（后续切片）、OAuth 路径变更、静态 api_key 变更、MCP server 端实现。

## Decisions

- **DA1 新鉴权类型，区别于静态 api_key**：`mcp_auth_models` 新增 per-user variant（如 `auth_type="api_key_per_user"`），字段含 header 风格（`Authorization: Bearer` 默认 / `X-API-Key`）+ 提交方式配置 `credential_input`（`form`默认 / `tool` / `both`）。静态 `api_key`（`key_env`）原样保留。**备选**：复用 `api_key` 加 `per_user` 布尔（否：与静态语义混淆、materialize/前端分支更乱）。

- **DA2 类型感知的 per-user 凭据存储（oauth vs static），不让 api-key 冒充 OAuth token**：`mcp_user_tokens` 是 OAuth 形状的（refresh/expires/scope/token_url/client_id/client_secret_env），api-key/bearer 一个都用不上。故给两侧 `mcp_user_tokens` 各加一列 **`credential_kind`（`oauth` 默认 / `static`）**（agent 侧 agent_state 内嵌迁移 v-next 回填 `oauth`；platform 侧 Alembic 111 回填 `oauth`）。`access_token_ciphertext` 重新语义化为**"per-request 注入的密钥密文"**：`oauth` kind 存 access token（并填 refresh/expiry/config 列）；`static` kind 只存那段 api-key/bearer 密钥，其余 OAuth 列 NULL。**bearer/api-key 同为 `static` kind，差别只在 `header_style`（server 配置，非 per-user 数据）**。取用/注入路径**仍统一复用**：`resolve_user_token(triple)` 返回密钥串、`_PerUserBearerAuth` 逐请求注入——注入时**查 server 的 `header_style`** 决定 `Authorization: Bearer` 还是 `X-API-Key`，凭据库只管密钥。**platform refresh 路径 MUST 跳过 `static` kind**（静态凭据无刷新；`expires_at` NULL 本就不触发，`credential_kind` 让其显式且防误用）。**备选**：另起独立 `mcp_user_credentials` 表（否：与 OAuth 三元组存储重复一套取用/managed 端点，且用户已选"类型感知统一"）。

- **DA3 无凭据触发与 OAuth 同构**：`call_tool` 无 token → 返回「需凭据」degrade 结果 → 触发提交流程。模式 1 经 `emit_*`/`set_authorization_link_deliverer` 同款 DM 投递；只是链接指向**凭据提交表单**而非授权 URL。

- **DA4 提交端点（表单），与 OAuth callback 同构但更简单**：
  - **standalone**：agent 自托管 `GET /mcp/credential?state=...`（渲染表单）+ `POST /mcp/credential`（state 校验 → 存本地库）。无 code 交换。
  - **managed**：platform 公开 `GET/POST /mcp/credential`（state 反查 → 存管理库）；pending（state→三元组）经 node loopback 登记（复用 `/nodes/{id}/mcp/oauth-pending` 同款，或新增 `credential-pending`）。`state` 一次性短 TTL，**身份只来自 state，不依赖登录态**。
  - **备选**：复用 OAuth 的 callback 端点（否：语义不同——OAuth 收 `code`、此处收用户填的 `key`；分开更清晰）。

- **DA5 对话内工具（模式 2，opt-in）**：内置 `set_mcp_credential(server_id, key)` 工具，仅当 server `credential_input ∈ {tool, both}` 时可见/可用；**限私信 DM**（频道里拒绝，提示走 DM 或表单），存 per-user 三元组。token 经工具入参 → 会进对话历史/trace → 故默认关闭、需 server 显式 opt-in。

- **DA6 两态经注入缝并存**：standalone 用本地库 + 自托管表单；managed 注入 resolver（已有）+ platform 表单端点 + node loopback。与 OAuth 切片同一 `FLEETENT_NODE_LOOPBACK_URL` 信号。

## Risks / Trade-offs

- [模式 2 token 进对话历史/trace] → 默认关闭（form-only），仅 server 显式 opt-in；工具限 DM；文档警示;可对工具入参做 trace 脱敏（复用 tool-arg-secret-redaction）。
- [提交链接是 bearer capability] → 仅 DM 投递、短 TTL、一次性、不可猜 state、HTTPS，与 OAuth state 同模型。
- [新增 auth_type 触及 raw34 的 auth_config 判别联合] → 纯新增 variant，静态 api_key/oauth 不动；materialize/前端加分支。
- [表单 XSS/CSRF] → 表单极简（单 input + 一次性 state 作 CSRF token）、提交即作废 state、key 不回显。

## Migration Plan

1. `mcp_auth_models` 加 per-user api-key variant + `credential_input` 配置 + materialize 翻译（纯新增）。
2. 两侧 `mcp_user_tokens` 加 `credential_kind`（agent 内嵌迁移 v-next + platform Alembic 111，回填 `oauth`）；store put/get 带 kind；platform refresh 跳过 `static`。凭据取用复用 `resolve_user_token`；确认 api-key 走通注入（http 按 header_style / stdio）。
3. 提交端点 + 表单：standalone 自托管 `GET/POST /mcp/credential`；managed platform 端点 + node loopback pending。
4. 无凭据触发 + DM 链接（模式 1）。
5. `set_mcp_credential` 工具（模式 2，DM-gated，opt-in）。
- **回滚**：per-user api-key 为新配置项;未配则全程走旧静态/或无;移除配置即回退;`mcp_user_tokens` 复用既有表，无新迁移（若需 header/类型列另议）。

## Open Questions

- 无（架构 brainstorming 锁定；表单样式/工具脱敏细节 apply 阶段按既有范式定）。
