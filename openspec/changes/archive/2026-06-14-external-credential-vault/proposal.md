## Why

fleetent 当前没有 **per-principal（按用户 / 按 agent）外部凭证**的能力：唯一为它搭过架子的 `connectors` + `agent_oauth_bindings` 两表彻底未接线（`_provider` 恒返回 `NeedsConsent`、`set_provider` 零调用方、零工具声明 `@tool(connector=)`、DB↔provider 之间无桥、`connectors.agent_id` 覆盖层从未写过非 NULL、admin 的 grants/revoke/offboarding 全是 placeholder），且**仅支持 OAuth**。现实里工具访问外部服务只能走 MCP 的**服务级**凭证（一份 key 从 env 来、全体用户共享）。v1 需要「Agent 以**调用用户本人**身份去访问 Google Drive / GitHub 等外部系统」，这要求每个用户绑定自己的授权、平台代存、调用时按身份取——服务级模型无法满足。

本变更把未接线的「工具 OAuth」脚手架**重设计**为一套 **per-principal 外部凭证库（Vault）**，并顺手把名实不符的表名归正。本次只交付一条端到端打通的最小纵切（tracer bullet）；完整终态与分期路线写入 design.md。

## What Changes

- **新增 per-principal 凭证库（Vault）核心**：
  - 新建 `external_credentials` 表，主键 `(user_id, service_id)`，存储**加密**的凭证负载（OAuth token 组 / API key）与状态；加密**复用**现有 `FLEETENT_SECRET_KEY` + Fernet（`secret_store.py` 的同一套对称加密），不引入新 master key。
  - principal 统一为 **User**：人是 User，agent 未来以 service-principal User 身份入库（本次只奠定 `user_id` 主键形状，agent 铸造留后续切片）。
  - 实现一个 **Vault provider**，platform 启动时经 `connectors.set_provider` 注入到现有 `connectors.py` seam；standalone agent 不注入 → 维持 `NeedsConsent`（符合 agent→platform 单向依赖）。
  - 最小 **OAuth2 授权码 consent 流**：authorize → 回调 → 换 token → 加密入库（首次 consent 必须用户本人完成）。
  - 一个**真实 builtin 工具**声明 `@tool(connector=...)`，端到端验证「按用户身份取到 per-user 凭证并执行」。
- **表名归正（随本切片落地，含 re-export shim 保兼容）**：
  - `connectors` → **`external_services`**（服务注册表；多协议；**移除** dormant 的 `agent_id` 覆盖层与其 partial 索引）。
  - `agent_oauth_bindings` → **`agent_service_grants`**（授权 join 去掉 "oauth" 字样，语义上承载 `run_as`(user|agent)；本切片完成重命名，run_as 字段语义在 design 中定义、按需在后续切片填充）。
- **不重复造轮子**：`api_keys`（INBOUND 认证调用方）、`agent_secrets`（服务级 env-slot 密钥）、`kb_connectors` / `im_connectors`（域前缀已合规）一律**保留不动**。
- **BREAKING**：`connectors.set_provider` 在 platform 部署下不再恒为 stub —— 声明了 `connector=` 的工具会按调用用户解析真实凭证；未授权用户得到 consent 提示而非旧 stub 的 `consent.invalid` 占位 URL。

## Capabilities

### New Capabilities
- `external-credential-vault`: per-principal 外部凭证库 —— 服务注册表（`external_services`）、加密的 per-(user, service) 凭证存储（`external_credentials`）、注入现有 seam 的 Vault provider、最小 OAuth2 授权码 consent 流。

### Modified Capabilities
- `agent-oauth-binding`: 绑定表 `agent_oauth_bindings` 重命名为 `agent_service_grants`，授权语义从「agent↔connector」泛化为「agent↔service + run_as(user|agent)」。
- `agent-scoped-connectors`: **移除** dormant 的 per-agent connector 覆盖层（`connectors.agent_id` 列、`ux_connectors_agent_scope` / `ux_connectors_global_scope` 索引、store 的 overlay 解析分支），随 `connectors`→`external_services` 重塑为单层全局服务注册表。其中 MCP server 的 per-agent 范围需求（同 spec 内）**不受影响、原样保留**。

> 注：`oauth-connector-admin` 描述的全 admin 面（per-user matrix / revoke / offboarding / lifecycle）本切片不 wire（属 roadmap P1/P5）；catalog 表 / store / 端点的 `connectors`→`external_services` 改名属**实现细节、非需求级行为变更**，靠 re-export shim 保 admin 运行时不破，故不在本切片列为 Modified Capability。

## Impact

- **owning package**：`platform/connector_management`（新增 vault 凭证 store + Vault provider + consent 端点；重塑 `connector_config_store` / `agent_oauth_binding_store` 命名）、顶层 `connectors.py`（seam 复用，被注入真 provider）。复用 `platform/agent_lifecycle/secret_store.py` 的 Fernet 加密（可抽共享 crypto helper）。
- **public API surface**：沿用 `connectors.get_credential(user_id, connector, scopes)` / `connectors.set_provider(provider)`（契约不变）；新增 Vault provider 实现与凭证 store 函数（`platform/connector_management` 内）；新增 consent 流的控制面端点（platform，不被 agent runtime import）。
- **owned tables**：**新增** `external_credentials`（加密 per-(user,service) 凭证）；**重命名** `connectors`→`external_services`（去 `agent_id` 列与两 partial 索引）、`agent_oauth_bindings`→`agent_service_grants`。`external_services` / `external_credentials` 不存 `client_secret`（secret 走 env / `agent_secrets`）。
- **config namespace**：**不新增**加密配置 —— 复用既有 `FLEETENT_SECRET_KEY`。服务注册项（authorize/token endpoint、client_id、scopes）落 `external_services` 表。
- **cross-module dependencies**：agent runtime 仅经 `connectors.py` seam **单向只读**取凭证；Vault provider 与 consent 端点全在 platform 侧，**不**反向 import；不触碰 `mcp-oauth2-auth`（MCP 传输层 client-credentials，另一码事）与 KB connector。守 `agent⊥platform` 契约。
- **migration / shim plan**：迁移号不在此写死（接当前 head 之后顺延）。重命名 `connectors`/`agent_oauth_bindings` 用「建新表 + 迁数据 + 改名」（SQLite 模式，对照迁移 085），并为 `connector_config_store` / `agent_oauth_binding_store` 旧模块路径保留 **re-export shim**（shim 不承载逻辑），使仅文字提及旧名的代码与运行路径不破。`delete_agent` 仅 `DELETE FROM agents`、靠 FK CASCADE 清理——`agent_service_grants` 重命名时保留 `FK→agents.id ON DELETE CASCADE`，行为不变。
- **不在范围（留后续切片 / 路线见 design.md）**：API-key 协议路径（Case 2b）、agent service-principal 铸造（Case 3）、wire admin 的 grants/revoke/offboarding/lifecycle placeholder、OAuth token 后台刷新与 revoke、多服务铺开。`connector-credential-injection` seam 契约**不改**（Vault 只是插入其后的 provider 实现）。仅文字提及旧表名的边缘 spec（`agent-definition` / `agent-admin-api` / `oauth-mcp-admin-ui` / `configuration` 等）的文案归正批量后置，本切片靠 re-export shim 保运行时不破。**不修改** `docs/architecture/data-model.md`。
