## Why

platform 的 OIDC web 登录(`admin-auth` 能力,归档 change `2026-06-22-oidc-web-login`)目前在回调里只校验 `email_verified===true`,**不校验邮箱域**。当 IdP 的 OAuth 同意屏幕为 External(典型如 Google Workspace 配置疏漏)时,任意 verified 的外部账号(如任意 gmail)都能登入并经 `resolve_or_provision` 自动建号——这是一个登录边界的安全缺口。当年那个切片已明确把"邮箱域限制"列为 deferred。本 change 补一个平台层的邮箱域白名单,把"谁能经 OIDC 进来"收回到平台配置控制,不再单纯依赖 IdP 侧设置。

## What Changes

- `OidcSettings` 新增字段 `allowed_email_domains: list[str]`,默认空列表。**空 = 不限制**(向后兼容,保持现有行为,OIDC 仍默认 disabled)。
- OIDC 回调在 `email_verified` 校验通过之后、`resolve_or_provision` 之前,新增一道**邮箱域闸**:取 verified email 的 `@` 后域,**大小写不敏感、精确匹配** `allowed_email_domains`;不在白名单则**拒登(403)**,不建号、不签 session。对新建用户与已有用户**一视同仁**。
- **provider 无关**:匹配 email 的域,**不读** Google 特有的 `hd` claim,遵守现有"不硬编码任何具体 provider"铁律。
- 域匹配为**精确匹配**:子域不自动包含(`eu.acme.com` 需显式列入)。配置为**全局单份**(per-tenant IdP 仍 deferred,本次不碰)。
- 更新 `platform.yaml.example` 的 `oidc` 段,加 `allowed_email_domains` 示例与注释。

非破坏:默认空名单时行为与现状完全一致;现有 OIDC 登录的其余行为(provider-agnostic、session、并号、共存、校验)均不变。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `admin-auth`: 在既有 "OIDC login via configured IdP" 之上**新增**一条"OIDC 邮箱域白名单"requirement——回调在 verified email 之后依配置的 `allowed_email_domains` 决定放行/拒登;空名单时与现状一致。既有 OIDC requirement 的行为不改(空名单语义下其所有 scenario 仍成立)。

## Impact

- **owning package**: `platform`(`src/fleetent/platform/user_management/oidc.py`、`user_admin_api.py`)+ 配置 `src/fleetent/oidc_config.py`。
- **public API surface**: 无新增端点;`/admin/oidc/callback` 行为在配置了白名单时新增一条 403 拒登路径。
- **owned tables**: 无(纯配置 + 校验逻辑,不动 DB/schema/迁移)。
- **config namespace**: `oidc.allowed_email_domains`(新增于既有 `oidc.*` 命名空间)。
- **cross-module dependencies**: 无新增;校验在 platform 内,不引入新依赖。
- **migration / shim plan**: 无数据迁移;新字段有默认值,旧配置零改动即向后兼容。
- **测试**:域匹配逻辑抽成纯函数 → unit 测(各种大小写/子域/空名单/多域);回调强制拒登行为 → integration 测(FastAPI + 配置注入)。`platform.yaml.example` 同步更新。
