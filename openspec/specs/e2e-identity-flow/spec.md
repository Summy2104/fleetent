# e2e-identity-flow Specification

## Purpose
TBD - created by archiving change e2e-identity-flow. Update Purpose after archive.
## Requirements
### Requirement: mock OIDC issuer e2e harness

项目 SHALL 提供一个 e2e mock OIDC issuer（`tests/e2e/_oidc_stub.py`，仿 `_llm_stub.py` 的进程内 ASGI app 形态），实现最小 OIDC provider 端点，使 platform 进程经 env 指向它即可走通真实 `/admin/oidc/login` → `/admin/oidc/callback` 流程，无需任何 src 改动。

#### Scenario: mock issuer 暴露发现与签名端点

- **WHEN** e2e 起 mock OIDC issuer
- **THEN** 它暴露 `/.well-known/openid-configuration`、`/oauth/authorize`（302 带 `code` + 透传 `state`）、`/oauth/token`（返回 RS256 签名的 `id_token`，claims 含 `iss`/`aud`/`sub`/`nonce`/`email`/`email_verified`）、jwks 公钥端点，且 platform 的 `OidcRelyingParty` 能用该 jwks 验过签名与 `nonce`

#### Scenario: OIDC 配置经 env 注入 platform 进程

- **WHEN** e2e 用 `OIDC__ENABLED` / `OIDC__ISSUER` / `OIDC__CLIENT_ID` / `OIDC__REDIRECT_URI` / `OIDC__TENANT` 及 `client_secret_env` 指定的 secret env 起 platform 进程
- **THEN** `Settings().oidc` 解析为 `enabled=True` 且指向 mock issuer，`GET /admin/oidc/login` 返回 302 到 mock issuer 的 authorize 端点

### Requirement: OIDC web 登录建 User e2e

SHALL 有一条 e2e 在多进程 managed 栈下，经真实 `GET /admin/oidc/login` → `GET /admin/oidc/callback` 完整流程，断言 OIDC 登录建出一个 User。

#### Scenario: OIDC 回调建出 User 并发 session

- **WHEN** httpx client（保留 cookie jar）请求 `GET /admin/oidc/login` 拿到 `fleetent_oidc_flow` cookie 与 authorize 跳转，再带 mock issuer 返回的 `code`/`state` 请求 `GET /admin/oidc/callback`
- **THEN** callback 经 `resolve_or_provision` 建出一个 User，其 `email` 等于 id_token claim、`tenant` 等于配置 tenant，且回调 302 到带 session token 的 `/admin/ui/login?token=`

### Requirement: email 并号收敛同一 user_id e2e

SHALL 有一条 e2e 验证：当一个 email 已先经其他路径（IM 担保身份或先建 User）存在时，以**同 email** 走 OIDC 登录 SHALL 收敛到**同一 user_id**、不重复建号。

#### Scenario: 先存在同 email 再 OIDC 登录不重复建号

- **WHEN** 同一 tenant 下先存在一个 email 为 `X` 的 User（经先行路径建立），随后以 id_token claim `email=X` 走 OIDC `/admin/oidc/callback`
- **THEN** `resolve_or_provision` 返回的 user_id 等于先前那个 User 的 user_id，users 表中该 tenant+email 仍只有一条记录（命中 `uq_users_tenant_email_not_null` 语义），不产生第二个 User

### Requirement: 跨渠道 /link 绑定与解绑 e2e

SHALL 有一条 e2e 经真实 HTTP 边界验证跨渠道 `/link`：`POST /admin/link/initiate`（session auth）拿 code → `POST /nodes/{id}/link-confirm`（node-key auth）确认 → im_users 绑定到该 user_id；并验证 `POST /admin/link/unlink` 解绑。

#### Scenario: initiate→link-confirm 把渠道身份绑到 User

- **WHEN** 以已登录 User 的 session token 请求 `POST /admin/link/initiate` 拿到 `code`，再以 node-key 请求 `POST /nodes/{id}/link-confirm` 带 `{platform, platform_user_id, code}`
- **THEN** link-confirm 经 `attach_identity` 把该 `(platform, platform_user_id)` 绑定到 initiate 的 user_id，响应返回该 user_id 与 tenant_id；后续 `get_mapped_user(platform, platform_user_id)` 映射到同一 user_id

#### Scenario: 重复或冲突 code 被拒

- **WHEN** 用已被消费的 code、或把已映射到他人的 `(platform, platform_user_id)` 再次 link-confirm
- **THEN** 前者返回 404（invalid or expired link code），后者返回 409（identity already mapped）

#### Scenario: unlink 解绑渠道身份

- **WHEN** 以 session token 请求 `POST /admin/link/unlink` 解绑已绑定的 `(platform, platform_user_id)`
- **THEN** 该渠道身份不再映射到原 user_id，`get_mapped_user` 返回空

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程身份流 e2e SHALL 在独立 slow/nightly lane 运行（`make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁（`make test-pr`）
- **THEN** 不运行本 change 的身份流 e2e（它们在独立 lane）

