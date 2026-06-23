## Why

现在人类登 web 只有**内置 admin 的 email/password**——真实企业员工无法登录。要让企业员工用公司既有身份登入（且不在 fleetent 给每人设密码），需要 **OIDC 登录**：员工 → 公司 IdP（自托管 Keycloak / Okta / Azure AD / Google Workspace 等）认证 → fleetent 据 verified email 找到/建 user、签 session。

这是车道 D 第一个**用户可见能力**（#3 是 plumbing、#2 是 provisioning 地基）。它**直接接 #2 的 `resolve_or_provision`** + 现有 `auth.create_session`，复用而非新建。

> `docs/architecture/identity-channel-ingress.md` 切片 #1。依赖 #2（已落地）。与 #4(IM-edge) 可并行（不同 surface：本切片在平台 login，#4 在 node IM-edge）。

## What Changes

- **provider-agnostic OIDC 客户端**：实现 OIDC relying party，经 discovery（`/.well-known/openid-configuration`）拿端点 → **不硬编码任何 provider**。连哪个 IdP 全是部署配置。
- **登录流程**：新增 `GET /admin/oidc/login`（authorize 重定向 + state/nonce 防 CSRF）+ `GET /admin/oidc/callback`（换 code、验 id_token、取 verified email → `resolve_or_provision(tenant, verified_email=email)` → `auth.create_session` → 带 session 回 SPA）。**fleetent 不接触/不存储员工密码**。
- **tenant 来源（决策 1 = A，C-ready）**：经一个**独立间接点** `_oidc_tenant_for(email, claims) -> tenant_id`；**A 实现 = 返回配置的单一 tenant**；将来 C（email 域→tenant 映射）只换这函数实现、零返工。
- **角色（默认）**：首次 OIDC 登录建的 user 给**基线角色**（viewer/member）；admin 另行指派；claims/groups→角色映射 deferred。
- **与内置 admin 密码共存（additive）**：email/password 登录保留（bootstrap）；OIDC 是新增第二条登录路径。
- **配置**：新增 `OidcSettings`（`enabled` 默认 OFF、`issuer`、`client_id`、`client_secret_env`、`redirect_uri`、`scopes`、`tenant`）；secret 走 env 引用、不入库。
- **库**：用 self-hostable OIDC 客户端（authlib），**无任何云托管 OIDC 服务依赖**。

### 不在本切片（deferred）
- C（email 域→tenant 映射）、B（per-tenant IdP）——只留 `_oidc_tenant_for` 间接点，将来扩。
- claims/groups → 角色映射（默认基线角色）。
- 普通员工登录后的**专用 web-chat 界面**（另一件事）——本切片只做 OIDC 认证 + 签 session + 解析/建 user，登录后落地走现有 SPA 的 role gate。
- IM 渠道（#4）、`/link`（#5）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `admin-auth`: 新增 **OIDC 登录方法**——经配置的 IdP 认证、用 verified email 经 `resolve_or_provision` 落到 email-keyed user、签现有 session；与内置 admin email/password 共存；首登建 user 给基线角色。同时澄清 **"无公开自注册"**：OIDC 首登的自动建 user 是 **IdP-gated**（只有公司 IdP 放行的人能进），不是公开自注册。

## Impact

- **owning packages**：`platform`（`user_management`：OIDC login/callback 端点 + 流程；`config` 新增 `OidcSettings`）；复用 `platform/im_gateway_management` 的 `resolve_or_provision` + `auth.create_session`
- **public API surface**：新增 `GET /admin/oidc/login`、`GET /admin/oidc/callback`；`OidcSettings` 配置
- **owned tables**：无——user 经 `resolve_or_provision`（#2）、session 沿用内存机制；OIDC state/nonce 为短时（签名 cookie / 内存），不建表
- **config namespace**：新增 `oidc`（OidcSettings；`enabled` 默认 OFF → 不配就零行为变化）
- **dependencies**：新增 `authlib`（self-hostable OIDC 客户端，无云依赖）
- **cross-module dependencies**：纯平台侧；复用 #2 的 `resolve_or_provision`（web 无 channel → 只按 email lookup-or-create、不写 im_users）；不碰 agent/node；不破坏解耦
- **migration / shim**：无 schema/迁移
- 与 #4(IM-edge) 并行不冲突（本切片 platform login，#4 node IM-edge）；不碰 server.py 的 chat ingress（与已落地 #3 零重叠）
