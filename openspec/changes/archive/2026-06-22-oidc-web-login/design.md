## Context

- 现有 login（`user_management/user_admin_api.py::login`）：`_resolve_login_user(email) → verify_password → auth.create_session(user.id) → {token, role, must_reset}`；session 为**内存** `token→{user_id, last_active}`（idle-timeout）。
- #2 已提供 `resolve_or_provision(tenant, *, verified_email=None, channel=None, platform_user_id=None) -> User`（web 无 channel → 只按 `(tenant, email)` lookup-or-create、不写 im_users）。
- 无 OIDC 客户端库（需加 authlib）。config 用 `*Settings`（如已落地的 `KnowledgeRetrievalAuditSettings`）。

## Goals / Non-Goals

**Goals:**
- provider-agnostic OIDC 登录（discovery 驱动，配置选 IdP），默认 OFF。
- 成功登录 → verified email → `resolve_or_provision` → 现有 session；与内置 admin 密码共存。
- tenant 经 `_oidc_tenant_for` 间接点（A=单 tenant，C-ready）。
- 安全：state/nonce 防 CSRF/重放；id_token 全套校验；**email 必须 verified 才信**。

**Non-Goals:**
- C（域→tenant）/B（per-tenant IdP）；claims→角色映射；普通员工专用 web-chat 界面；IM(#4)/link(#5)。

## Decisions

- **D1 · provider-agnostic（discovery + authlib）。** 经 `issuer/.well-known/openid-configuration` 拿 authorize/token/jwks 端点；用 **authlib**（self-hostable、无云依赖）做 RP。不写任何 per-provider 分支。Google 等只是 issuer 配置值（带云 caveat，客户自选）。
- **D2 · 流程**：
  - `GET /admin/oidc/login`：构造 authorize URL（含 `state`+`nonce`+`redirect_uri`+`scopes`），重定向到 IdP。
  - `GET /admin/oidc/callback`：校验 `state` → 用 code 换 token → **校验 id_token**（JWKS 验签、`iss`==配置 issuer、`aud`==client_id、`exp`/`iat`、`nonce` 匹配）→ 取 `email` + **要求 `email_verified==true`** → `resolve_or_provision(_oidc_tenant_for(email,claims), verified_email=email)` → `auth.create_session(user.id)` → 带 session 重定向回 SPA。
- **D3 · tenant 间接点（决策 1=A，C-ready）**：`_oidc_tenant_for(email, claims) -> tenant_id`，A 实现返回 `OidcSettings.tenant`（配置的单一 tenant）。C 将来只换此函数为域映射，零返工。
- **D4 · state/nonce 用短时签名 cookie（无状态）**：避免内存态在多 worker / 重启下丢失；cookie 短 TTL、HttpOnly、SameSite。（也可内存 keyed by state，但签名 cookie 更稳。）
- **D5 · 角色 + 共存**：首登建 user 给基线角色（沿用 `create_user`/role 默认 viewer）；email/password 登录路径完全保留。
- **D6 · 配置**：`OidcSettings { enabled=False, issuer, client_id, client_secret_env, redirect_uri, scopes=["openid","email"], tenant }`；client_secret 走 env 引用（沿用 secret-reject-inline 约定），默认 OFF。

## Risks / Trade-offs

- **★email_verified 是身份信任的命门**：必须 `email_verified==true` 才把 email 当 join key；否则拒登（否则攻击者在 IdP 端塞个未验证 email 就能冒充已存在 user）。测试必须覆盖"email_verified=false / 无 email → 拒"。
- **id_token 全套校验不可偷工**：JWKS 验签 + iss + aud + exp + nonce，缺一不可（authlib 提供，但要确认全开）。测试覆盖各项失败 → 拒。
- **redirect_uri 必须与 IdP 注册一致**：配置项，部署时对齐；不匹配 IdP 会拒。
- **多 worker / 重启下的 state**：用签名 cookie（D4）避免内存态丢失；若用内存态，需注意 platform 多 worker 场景。
- **create_user 总发 api_key**：OIDC web 用户也会拿到一把 key（#2 已记为观察）；可接受，注意别把"web 登录身份"与"程序 key"语义混。
- **clock skew**：exp/iat 校验留小容差。
