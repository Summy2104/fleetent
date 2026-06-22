## 1. 配置 + tenant 间接点 + 依赖

- [x] 1.1 **测试（红）**：`OidcSettings` 默认 `enabled=False`；字段 issuer/client_id/client_secret_env/redirect_uri/scopes/tenant 解析正确；client_secret 走 env 引用、inline secret 被拒（沿用现有 secret-reject）。`_oidc_tenant_for(email, claims)` 返回 `OidcSettings.tenant`（A 实现）。先跑见红。
- [x] 1.2 **实现（绿）**：`config` 加 `OidcSettings`（默认 OFF）；加 `_oidc_tenant_for` 独立函数（A=返回配置 tenant，注释标 C-ready）；`pyproject.toml` 加 `authlib` 依赖。跑见绿。

## 2. OIDC RP 客户端（discovery + authorize + callback 校验）

- [x] 2.1 **测试（红）**：用 respx mock 一个 IdP（discovery `/.well-known/openid-configuration` + jwks + token 端点）+ 测试签名私钥：
  - 构造 authorize URL 含 state+nonce+redirect_uri+scopes；
  - callback：code 换 token → **id_token 校验全套**（JWKS 验签、`iss`==配置、`aud`==client_id、`exp`/`iat`、`nonce` 匹配）→ 取 email；
  - ★ `email_verified != true` 或无 email → **拒**；
  - 各校验失败（坏签名/iss/aud/过期/nonce/state）→ **拒**。先跑见红。
- [x] 2.2 **实现（绿）**：`platform/user_management` 下 OIDC RP 模块（authlib）：discovery、build_authorize、exchange+validate。跑见绿。

## 3. login/callback 端点 → resolve_or_provision + session

- [x] 3.1 **测试（红，integration 真 DB）**：`GET /admin/oidc/login` 302 到 IdP（带 state cookie）；`GET /admin/oidc/callback`（fake IdP 回有效 id_token）→ (a) email 无对应 user → 在 `_oidc_tenant_for` tenant 下建 email-keyed user（基线角色）+ 签 session；(b) email 命中既有 user → 解析到该 user 不重复建 + 签 session（attach-only 并号）。先跑见红。
- [x] 3.2 **实现（绿）**：`/admin/oidc/login` + `/admin/oidc/callback` 端点：state/nonce 经短时签名 cookie；callback 校验后 `resolve_or_provision(_oidc_tenant_for(email,claims), verified_email=email)` → `auth.create_session` → 带 session 重定向回 SPA。跑见绿。

## 4. 共存 / 关闭 / 安全 收尾

- [x] 4.1 **测试（红）**：(a) OIDC `enabled=True` 时内置 admin email/password 登录**仍正常**（共存）；(b) `enabled=False`（默认）时 OIDC 入口不可用、password 登录行为不变；(c) `email_verified=false` 的 callback → 拒、不签 session、不建 user。先跑见红。
- [x] 4.2 **实现（绿）**：enabled 门控（OFF 时端点不挂/返回明确禁用）；确认 password 路径零改动。跑见绿。
- [x] 4.3 **收尾**：`make test-pr` 全绿（对照 main 基线无新增失败）+ 跑 `uv run pytest tests/integration/test_auth.py tests/unit/test_auth.py -q`（+ 新增 OIDC 测试文件）无新增失败；新增 authlib 依赖后 `uv sync` 正常、覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
