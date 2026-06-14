## Context

fleetent 的「凭证」此前散落在 5 处、跨两个相反方向，从未拉通设计：

```
INBOUND（谁在调用我）
  └ api_keys                认证调用方的 ma- bearer（load-bearing，本设计不动）

OUTBOUND（我拿什么去调别人）
  ├ MCP server auth (env)   服务级/共享：auth_type=none|api_key|oauth2，
  │                         api_key 读 os.environ[api_key_env]，oauth2 是
  │                         client-credentials(M2M) —— 整台 server 一份凭证
  ├ agent_secrets           per-agent/shared 命名 env-slot 密钥（加密，Fernet +
  │                         FLEETENT_SECRET_KEY），是上面服务级 auth 的后端
  ├ kb_connectors           per-(tenant,kb) 数据源同步授权（KB 域自管）
  └ connectors +            ★未接线：本欲做「per-user OAuth 授权码」，但缺 token 表 /
    agent_oauth_bindings       consent 流 / 桥，且仅 OAuth、agent_id 覆盖层 dormant、
                               admin 全 placeholder
```

唯一缺的一整列是 **per-principal（按用户 / 按 agent）外部凭证**。`connectors.py` 已有一个干净且有测试的进程内 seam（`get_credential(user_id, connector, scopes)` 委派给可替换 `_provider`，dispatch 注入隐藏 `client` / `NeedsConsent` 短路），但其 `_provider` 恒为 stub。本设计补齐这一列，复用该 seam 作为取数咽喉。

约束：(1) `agent⊥platform` 单向依赖铁律 —— agent runtime 不得反向 import platform；(2) 数据主权 —— 凭证 secret 必须加密落盘，禁云托管 KMS；(3) standalone agent（无 platform）必须仍能 `fleetent agent run`，此时无 Vault → 声明 connector 的工具自然不可用。

## Goals / Non-Goals

**Goals:**
- 建立 per-principal 外部凭证库（Vault）的**终态架构**与命名，并落一条端到端打通的最小纵切。
- principal 统一为 User（人 = User，agent = service-principal User），使「per-user 凭证」(Case 2) 与「agent 自身身份凭证」(Case 3) 共用同一张表、同一套解析。
- 复用既有 seam（`connectors.py`）与既有加密（Fernet + `FLEETENT_SECRET_KEY`），不重复造轮子。
- 把名实不符的表名一次归正（`connectors`→`external_services`、`agent_oauth_bindings`→`agent_service_grants`）。

**Non-Goals（本切片）:**
- 不做 API-key 协议路径（Case 2b）、不铸造 agent service-principal（Case 3 实体）、不 wire admin 的 grants/revoke/offboarding/lifecycle、不做 token 后台刷新 / revoke、不铺多服务。以上为终态 roadmap 的后续 phase。
- 不改 `connector-credential-injection` seam 契约（Vault 仅为其后的 provider 实现）。
- 不并入 KB connector（KB 独立域）、不触碰 MCP 传输层 OAuth（`mcp-oauth2-auth`，client-credentials/M2M，与 per-user 无关）。
- 不修改 `docs/architecture/data-model.md` 与 `openspec/specs/` 主 specs（delta 写在本 change 目录）。

## Decisions

### D1. 凭证归属轴 = principal（User），不是 agent 也不是 tenant
- **决定**：Vault 凭证主键为 `(user_id, service_id)`。`user_id` 即 `users.id`（TEXT）。agent 自身身份凭证（Case 3）= 给 agent 一个 service-principal User 行后，复用同一主键。
- **为什么**：与既有身份模型「一切是 User」「`SYSTEM_OWNER_ID = "__system__"` 这种非人类 principal 已用 User id 表达」一致；让 Case 2/3 合一，避免 `principal_type` 双轴带来的解析 / 审计分叉。
- **备选**：principal 双轴（`user_id | agent_id` + 判别符）—— 显式但割裂 Case 2/3，解析两条路，弃。

### D2. 复用 `connectors.py` seam 作为取数咽喉，platform 注入 Vault provider
- **决定**：保留 `get_credential` / `set_provider` 契约不变；platform 启动时 `connectors.set_provider(vault_provider)`（对标 `user_store.set_api_key_resolver` 的注入式解耦）。standalone agent 不注入 → 默认 `_default_provider` 仍返回 `NeedsConsent`。
- **为什么**：seam 已为「provider 返回真 Credential」设计且有测试；注入式让 agent runtime **只读、不反向 import** platform，守单向依赖；standalone 退化为「无凭证」是正确语义。
- **备选**：让 dispatch 直接查 DB —— 破坏 agent⊥platform，弃。

### D3. 加密复用 Fernet + `FLEETENT_SECRET_KEY`，不新增 master key
- **决定**：`external_credentials` 的凭证负载用 `secret_store.py` 同一套 Fernet 对称加密；将 `_fernet()` 抽为可共享的 crypto helper（agent_secrets 与 vault 共用）。
- **为什么**：已存在、on-prem 友好、零新增配置面；统一密钥管理，降低运维与误配风险。
- **备选**：新 vault 专属 master key —— 多一个 secret 要管，无收益，弃。

### D4. principal × 表结构（终态）
```
external_services（注册表，重塑自 connectors —— 去 agent_id 覆盖层）
  service_id PK, kind, protocol(oauth2_authcode|api_key),
  authorize_url, token_url, client_id, scopes, enabled, created_at, updated_at
  —— 不存 client_secret（走 env / agent_secrets）

external_credentials（★新建 —— 当前缺失的那张）
  PK (user_id, service_id)
  payload_ciphertext  （Fernet 加密：oauth{access,refresh,expires,scopes} | api_key{value}）
  status(authorized|needs_consent|needs_reauth|error)
  updated_at, updated_by
  —— FK user_id→users.id（与 api_keys 同侧，软引用按现有惯例）

agent_service_grants（授权 join，重塑自 agent_oauth_bindings）
  PK (agent_id, service_id)
  run_as(user|agent)          ← 决定 dispatch 取 (调用用户|agent principal) 的凭证
  created_at, created_by
  FK agent_id→agents.id ON DELETE CASCADE   ← 保留，delete_agent 行为不变
```

### D5. run_as 在 grant 层声明，不在每次调用传
- **决定**：「以用户身份 / 以 agent 身份」由 `agent_service_grants.run_as` 声明；dispatch 据此决定向 Vault provider 传 `调用用户 user_id` 还是 `agent 的 service-principal user_id`。
- **为什么**：归属是绑定级策略而非每调用决策；避免把身份选择暴露给 LLM / 调用参数。
- **本切片**：run_as 字段语义在此定义；tracer bullet 走 `run_as=user`（默认），字段填充与 agent 分支留后续切片。

### D6. consent 流（最小，platform 控制面）
- authorize 端点：构造 provider 授权 URL（带 state/PKCE），返回给用户本人浏览器。
- callback 端点：校验 state → 用 code 换 token → Fernet 加密 → 写 `external_credentials`，status=authorized。
- **首次 consent 必须用户本人完成**（沿用旧 admin guard：admin 不能代授权）。
- 本切片只做「authorize + callback + 换 token 入库」打通一个 service；refresh / revoke / 多 provider 留后续。

### D7. 表名归正随本切片落地 + re-export shim
- `connectors`→`external_services`、`agent_oauth_bindings`→`agent_service_grants`，用「建新表+迁数据+改名」（SQLite 模式，对照迁移 085）。
- `connector_config_store` / `agent_oauth_binding_store` 旧模块路径保留 **re-export shim**（不承载逻辑），使仅文字引用旧名的代码与运行路径不破；边缘 spec 文案归正批量后置。

## 终态 Roadmap（分期切片，本次只交付 P0）

| Phase | 内容 | 本次 |
|---|---|---|
| **P0** | tracer bullet：`external_credentials` 表(加密) + 最小 OAuth2 consent 流 + Vault provider 经 `set_provider` 接线 + 1 个真工具 `@tool(connector=)` 端到端取到 per-user 凭证；连带表名归正(去 agent_id 覆盖层) | ✅ |
| P1 | `external_services` 注册表完整 CRUD（admin 接线，替换 placeholder） | 后续 |
| P2 | OAuth token 后台刷新 / 过期处理 / revoke；status 流转 needs_reauth | 后续 |
| P3 | API-key 协议路径（Case 2b）：用户把外部服务 key 交平台、加密入 `external_credentials` | 后续 |
| P4 | `agent_service_grants` 的 run_as=agent + agent service-principal User 铸造（Case 3） | 后续 |
| P5 | wire admin grants/revoke/offboarding/lifecycle（disabled user → 级联吊销凭证） | 后续 |
| P6 | 多服务铺开 + provider 适配层（google-drive / github / confluence …） | 后续 |
| P7 | 边缘 spec 文案与 data-model.md 一次性对账归正 | 后续 |

## Risks / Trade-offs

- **[表重命名涟漪]** 多个 spec / 代码文字提及旧表名 → re-export shim 保运行时不破 + 文案归正后置（P7）；本切片只改直接拥有这些表的 spec（agent-oauth-binding / agent-scoped-connectors / oauth-connector-admin）。
- **[BREAKING：provider 不再恒 stub]** platform 部署下声明 connector 的工具行为改变 → 本切片只引入 1 个真工具且需显式 grant，影响面可控；未授权用户得到真实 consent 提示而非占位 URL。
- **[加密密钥单点]** `FLEETENT_SECRET_KEY` 丢失 → 凭证不可解密 → 与现有 `agent_secrets` 同风险面，运维已有该 key 的管理约定，不新增风险类别。
- **[standalone agent 无凭证]** 无 platform 时声明 connector 的工具不可用 → 这是符合单向依赖的正确语义，文档说明即可。
- **[principal=User 需要 agent 入 users 表]** Case 3 依赖给 agent 铸 service-principal User → 本切片不实现，仅奠定 `user_id` 主键形状，避免提前耦合。

## Migration Plan

1. 迁移（号接 head 顺延，不写死）：建 `external_credentials`；重命名 `connectors`→`external_services`（建新表去 `agent_id` 列 + 两 partial 索引、迁数据、改名）；重命名 `agent_oauth_bindings`→`agent_service_grants`（保 `FK→agents.id ON DELETE CASCADE`，加 `run_as` 列默认 `user`）。
2. 抽共享 Fernet crypto helper；实现 Vault provider；platform 启动 `set_provider` 接线。
3. consent 端点（authorize/callback/换 token 入库）。
4. 1 个真 builtin 工具声明 `@tool(connector=...)`；端到端验证。
5. 旧 store 模块路径留 re-export shim。
- **Rollback**：迁移 downgrade 反向重命名并恢复旧表形状；`set_provider` 不注入则 seam 退回 stub（功能整体回退、不破 standalone）。

## Open Questions

- `external_credentials.user_id` 是否加 `FK→users.id`（与 api_keys 一致走软引用，还是收紧为硬 FK + CASCADE）？倾向与 api_keys 保持一致，留实现时定。
- service-principal User 的 id 形态（`agent:<id>` vs UUID + `role=service`）—— 留 P4 设计。
- consent 端点的挂载路径与鉴权（platform 既有 session auth 复用）—— 留实现时与 oauth-connector-admin 现有 guard 对齐。
