## Why

登录页(`frontend/src/app/routes.tsx`)的「使用 SSO 登录」按钮有两个问题:(1) **无条件渲染**——即使 OIDC 未启用也显示,用户点击打到 `/admin/oidc/login` 得到 404 "oidc disabled",是个死入口;(2) **文案写死** i18n 的 "Sign in with SSO",配了 Google 也无法显示成"使用 Google 登录"。根因相同:登录页是 pre-auth,平台没暴露任何让它得知"OIDC 是否启用、入口该叫什么"的途径(无公开配置端点)。本 change 让 SSO 入口按真实启用状态显示、文案可配,把 Google/SSO 登录的入口体验补完整。

## What Changes

- 后端新增**免鉴权** `GET /admin/oidc/config`,返回 `{enabled: bool, label: str}`。**只暴露这两项**,绝不返回 `client_secret` / `issuer` / `client_id` 等。未启用时正常返回 `200 {enabled: false, label: ""}`(不复用会抛 404 的 `_require_oidc_settings`)。
- `OidcSettings`(`src/fleetent/oidc_config.py`)新增 `button_label: str = ""`(默认空)。config 端点的 `label` = `settings.button_label`。
- 前端登录页启动期 fetch `/admin/oidc/config`:`enabled=false` 时**不渲染** SSO 按钮;`enabled=true` 时渲染,按钮文案 = `label`(非空时)否则回落现有 i18n `login.signInWithSso`。
- `platform.yaml.example` 的 `oidc` 段加 `button_label` 示例 + 注释(如 `"Sign in with Google"`)。

非破坏:`button_label` 默认空 → 文案与现状一致;新端点为新增。唯一可见行为变化 = 未启用 OIDC 时登录页不再显示死按钮(修 bug)。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `admin-auth`: 在既有 "OIDC login via configured IdP" 之上**新增**一条 requirement——平台经免鉴权配置端点暴露 OIDC 启用状态与可配置入口文案(零敏感信息);登录入口 SHALL 仅在 OIDC 启用时呈现。既有 OIDC 登录行为不变。

## Impact

- **owning package**: `platform`(`src/fleetent/platform/user_management/user_admin_api.py` 新端点)+ 配置 `src/fleetent/oidc_config.py`;前端 `frontend/src/app/routes.tsx`(登录页)+ i18n。
- **public API surface**: 新增 `GET /admin/oidc/config`(免鉴权,只读,返回 `{enabled, label}`)。
- **owned tables**: 无(纯读配置,不动 DB/schema/迁移)。
- **config namespace**: `oidc.button_label`(新增于既有 `oidc.*`)。
- **cross-module dependencies**: 无新增,纯 platform 内;不触碰 agent/platform 解耦铁律。
- **migration / shim plan**: 无数据迁移;新配置字段有默认值,旧配置零改动向后兼容。
- **测试**:后端端点(含未启用 → `enabled:false`、启用 → `enabled:true`+label、不泄漏 secret)用 integration 测;前端条件渲染 + 文案回落用组件测;`platform.yaml.example` 同步更新。
- **安全**:端点免鉴权但只读 `enabled` + `button_label`,无 secret/issuer/client_id 外泄。
