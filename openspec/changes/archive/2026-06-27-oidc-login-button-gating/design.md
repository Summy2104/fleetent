## Context

OIDC web 登录已落地(`admin-auth`)。登录页 `frontend/src/app/routes.tsx:142-150` 无条件渲染一个「使用 SSO 登录」按钮(`login.signInWithSso`),点击 `window.location.href = ${baseUrl}/admin/oidc/login`。后端 `/admin/oidc/login`(免鉴权)在未启用时经 `_require_oidc_settings()` 抛 `404 "oidc disabled"`。登录页是 pre-auth,拿不到 `/admin/me`(post-auth),也没有任何端点告诉它 OIDC 是否启用 / 入口文案——故按钮既无法条件显示,也无法改名。

## Goals / Non-Goals

**Goals:**
- 登录页按真实 OIDC 启用状态决定是否显示 SSO 入口(修死按钮 bug)。
- 入口文案可配置(让配 Google 的部署能显示"Sign in with Google")。
- 暴露状态的端点免鉴权但零敏感信息泄漏。

**Non-Goals:**
- 多 IdP / 多按钮(单份全局 OIDC 配置,per-tenant IdP 仍 deferred)。
- Google logo / 图标按钮(需打包静态资源,且与自托管 CSP 无关收益低;只做文案)。
- 改动 OIDC 登录/回调既有逻辑。

## Decisions

**D1 — 新增独立的免鉴权 `GET /admin/oidc/config`,不复用 `_require_oidc_settings`。** 该 handler 直接读 `Settings().oidc`,返回 `{enabled, label}`;未启用也返回 `200 {enabled:false, label:""}`。理由:`_require_oidc_settings` 的契约是"未启用即 404",用于 login/callback 的硬门;而 config 端点的契约是"永远可查、如实报告启用与否",语义相反,必须分开。备选(在 `/admin/me` 加字段)被否:`/admin/me` 是 post-auth,登录页用不了。

**D2 — 响应模型显式只含 `enabled` + `label`(白名单,而非从 OidcSettings 序列化)。** 用一个独立的小 response model / dict 显式构造,**不**直接把 `OidcSettings` 丢出去。理由:防止将来给 OidcSettings 加字段时意外泄漏(secret/issuer)。安全测试断言响应键集合 == `{enabled, label}`。

**D3 — `label` 是自由文本配置 `oidc.button_label`,空时前端回落 i18n。** 不做 provider 名→文案的自动映射。理由:自由文本最灵活(运营可写任意语言的"使用 Google 登录");默认空则保持现有 i18n 双语行为不变。代价:`button_label` 一旦配置就是单一字符串、不随前端语言切换——可接受(运营按部署主语言配一次)。

**D4 — 前端用 React Query fetch config,enabled 为假则整块不渲染。** 登录页已用 `@tanstack/react-query`。新增 `useOidcConfigQuery`(无需 auth),`enabled===true` 才渲染按钮;文案 `config.label || t('login.signInWithSso')`。加载中/请求失败 → 视作未启用(不渲染),fail-safe 不显示死按钮。

## Risks / Trade-offs

- **[免鉴权端点泄漏配置] → Mitigation**:D2 白名单式构造响应,只出 `enabled`+`label`;integration 测显式断言响应键集合与不含 secret/issuer 子串。
- **[config 请求失败时登录页该如何] → Mitigation**:fail-safe——加载中或失败一律不渲染 SSO 入口(宁可少一个入口,不放死按钮);email/password 登录不受影响、始终可用。
- **[button_label 不随语言切换] → Mitigation**:文档说明这是部署级单值;不配则保持现有双语 i18n 默认。

## Migration Plan

1. 后端:加 `OidcSettings.button_label`(默认空)+ `GET /admin/oidc/config` + integration 测。
2. 前端:加 `useOidcConfigQuery` + 登录页条件渲染 + 组件测 + i18n(默认文案已有)。
3. `platform.yaml.example` 加 `button_label` 注释示例。
4. 回滚:纯 `git revert`;无 DB/状态。旧配置无 `button_label` → 默认空 → 行为同现状。

## Open Questions

- 无。端点形状、字段、安全边界均已定。
