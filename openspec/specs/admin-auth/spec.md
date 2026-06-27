# admin-auth Specification

## Purpose
TBD - created by archiving change 2026-05-30-user-management. Update Purpose after archive.
## Requirements
### Requirement: Three-tier roles
Users SHALL have a `role` of `built_in_admin`, `admin`, or `viewer`. `/admin/*` access SHALL require `role` in {`admin`, `built_in_admin`}; write operations SHALL be denied to `viewer`. This `role` replaces the boolean `is_admin`; for compatibility `is_admin` is true iff `role` is in {`admin`, `built_in_admin`}.

#### Scenario: Viewer blocked from write
- **WHEN** a `viewer` calls a write endpoint under `/admin`
- **THEN** the response is 403 and no change is persisted

#### Scenario: Admin allowed
- **WHEN** an `admin` calls `GET /admin/users`
- **THEN** the response is 200

### Requirement: Built-in admin seeding
On first startup with no admin present, the system SHALL seed a built-in admin with a fixed username, a generated temporary password written to the startup log, `must_reset=1`, and `role=built_in_admin`.

#### Scenario: Seed on first boot
- **WHEN** the server starts and no built-in admin exists
- **THEN** a `built_in_admin` user is created with `must_reset=1` and the initial password is written to the startup log

#### Scenario: Idempotent seed
- **WHEN** the server starts and a built-in admin already exists
- **THEN** no new admin is created and no password is logged

### Requirement: Forced password reset on first login
A user with `must_reset=1` SHALL be forced to change the password before accessing any other page.

#### Scenario: Must-reset gate
- **WHEN** the built-in admin logs in with the initial password and `must_reset=1`
- **THEN** access to any page other than the change-password flow is rejected until the password is changed, after which `must_reset` is cleared

### Requirement: Built-in admin is protected
The built-in admin SHALL NOT be deletable, renamable, or demotable by anyone; only the built-in admin may change its own password.

#### Scenario: Delete/demote built-in admin rejected
- **WHEN** any user (including another admin) attempts to delete, rename, or demote the built-in admin
- **THEN** the operation is rejected and nothing is persisted

#### Scenario: Regular admin cannot block built-in admin
- **WHEN** a non-built-in admin attempts to block or demote the built-in admin
- **THEN** the operation returns 403 and nothing is persisted

### Requirement: Email/password login with idle timeout
The system SHALL authenticate admins via email + password, issuing a server-side login session distinct from the `/chat` Bearer API key, and SHALL log out sessions after an idle timeout.

#### Scenario: Login issues a session
- **WHEN** a user submits a correct email/password
- **THEN** a login session is established

#### Scenario: Idle timeout logs out
- **WHEN** a login session is idle beyond the configured timeout
- **THEN** the next request requires re-authentication

### Requirement: No public self-registration
The system SHALL NOT expose a public self-registration endpoint。任何人 SHALL NOT 能在无凭据的情况下自助创建账号。

OIDC 首次登录的自动建 user **不属于**公开自注册：它是 **IdP-gated**——只有公司 IdP 认证放行的人才会被建 user，建号的"准入门"是公司 IdP（运维通过配置/IdP 侧成员管理控制谁能登），不是一个面向公众的注册端点。

#### Scenario: Register path absent
- **WHEN** a visitor requests `/register`
- **THEN** the response is 404 or an explicit "contact your administrator" message, with no way to self-create an account

#### Scenario: OIDC 建号受 IdP 门控、非公开自注册
- **WHEN** 经 OIDC 首次登录自动建 user
- **THEN** 仅在该用户已被公司 IdP 认证放行时发生；未被 IdP 认证者无法借此建号（准入门在 IdP，不是公开端点）

### Requirement: OIDC login via configured IdP

系统 SHALL 支持经配置的 OIDC IdP 登录 web，作为内置 admin email/password 之外的**第二条登录路径**（两者共存）。系统 SHALL 实现 **provider-agnostic 的 OIDC relying party**：经 IdP discovery（`/.well-known/openid-configuration`）解析端点，**不硬编码任何具体 provider**——连哪个 IdP（自托管 Keycloak / Okta / Azure AD / Google Workspace 等）纯由部署配置（issuer / client_id / client_secret(env 引用) / redirect_uri / scopes）决定。OIDC 默认 **disabled**，未配置则零行为变化。

登录成功后系统 SHALL 用 id_token 的 **verified email** 经 `resolve_or_provision`（按 `(tenant, email)` 找到或建 email-keyed user）解析出 user，并签发**与现有 email/password 登录同一套**的 server-side session（OIDC 不新增第三种认证模型，只是多一种"确立身份→签 session"的 edge）。tenant 经一个独立间接点 `_oidc_tenant_for(email, claims)` 求得（当前实现 = 配置的单一 tenant）。fleetent **MUST NOT** 接触或存储用户在 IdP 的密码。

state/nonce SHALL 用于防 CSRF / 重放；id_token 的签名、issuer、audience、过期 SHALL 校验。

#### Scenario: 新员工经 OIDC 首次登录

- **WHEN** 一个 IdP 已验证的员工首次经 OIDC 登录，verified email 在库中无对应 user
- **THEN** 在 `_oidc_tenant_for` 求得的 tenant 下建一个 email-keyed user（基线角色），签发 session

#### Scenario: 既有 user 经 OIDC 登录

- **WHEN** verified email 命中既有 user
- **THEN** 解析到该 user（不重复建），签发 session（与 #2 的 attach-only 并号一致）

#### Scenario: 与内置 admin 密码共存

- **WHEN** OIDC 已配置启用
- **THEN** 内置 admin 仍可用 email/password 登录；两条路径并存

#### Scenario: 未配置即关闭

- **WHEN** OIDC 未配置（disabled）
- **THEN** OIDC 登录入口不可用，email/password 登录行为不变

#### Scenario: 校验失败拒绝

- **WHEN** callback 的 state/nonce 不匹配，或 id_token 签名/issuer/audience/过期校验失败
- **THEN** 登录被拒，不签发 session

### Requirement: OIDC 登录受邮箱域白名单门控

当 OIDC 启用时,系统 SHALL 支持经配置项 `allowed_email_domains`(`OidcSettings` 下的字符串列表)限制哪些邮箱域可经 OIDC 登录。该校验 SHALL 在回调中 **`email_verified` 校验通过之后、`resolve_or_provision` 之前**执行:取 id_token verified email 的 `@` 之后域,**大小写不敏感**地**精确匹配**白名单中任一项则放行,否则 SHALL 拒登(HTTP 403,detail 明确指出域不被允许),且 MUST NOT 建号、MUST NOT 签发 session。

`allowed_email_domains` 为**空**时 SHALL 不施加任何域限制(向后兼容,行为与未加该字段前一致)。匹配 SHALL 为**精确域匹配**:子域不自动包含(`eu.acme.com` 不被 `acme.com` 覆盖,需显式列入)。该校验 SHALL **provider 无关**——基于 email 域判定,MUST NOT 依赖任何 provider 专有 claim(如 Google 的 `hd`)。域门控 SHALL 对**新建用户与已有用户一视同仁**(命中既有 user 的域外邮箱同样被拒登)。

#### Scenario: 域外邮箱被拒登

- **WHEN** `allowed_email_domains=["acme.com"]`,一个 verified email 为 `eve@gmail.com` 的身份经 OIDC 回调登录
- **THEN** 回调返回 403,不建号、不签 session

#### Scenario: 域内邮箱放行

- **WHEN** `allowed_email_domains=["acme.com"]`,verified email 为 `Alice@ACME.com`(大小写混合)
- **THEN** 域校验通过(大小写不敏感),照常 `resolve_or_provision` 并签发 session

#### Scenario: 空名单不限制

- **WHEN** `allowed_email_domains=[]`(默认)
- **THEN** 不施加域限制,任何 verified email 照既有 OIDC 流程登录

#### Scenario: 子域不被父域自动覆盖

- **WHEN** `allowed_email_domains=["acme.com"]`,verified email 为 `bob@eu.acme.com`
- **THEN** 回调返回 403(子域未显式列入,不被 `acme.com` 覆盖)

#### Scenario: 已有 user 的域外邮箱同样被拒

- **WHEN** `allowed_email_domains=["acme.com"]`,某 verified email 命中库中既有 user 但其域不在白名单
- **THEN** 回调返回 403,不签发 session(域门控先于身份解析,对已有 user 一视同仁)

