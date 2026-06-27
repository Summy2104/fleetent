## ADDED Requirements

### Requirement: OIDC 登录入口可发现且按启用状态门控

平台 SHALL 提供一个**免鉴权**的只读端点 `GET /admin/oidc/config`,供 pre-auth 的登录界面发现 OIDC 登录入口状态。该端点 SHALL 返回 `{enabled: bool, label: str}`:`enabled` = OIDC 是否启用;`label` = 可配置的入口文案(`OidcSettings.button_label`,默认空字符串)。该端点 MUST NOT 返回任何敏感配置(client_secret / client_id / issuer / redirect_uri 等)。OIDC 未启用时该端点 SHALL 返回 `200` 且 `enabled=false`(MUST NOT 返回 404 或错误)。

登录界面 SHALL 仅在 `enabled=true` 时呈现 OIDC 登录入口;`enabled=false` 时 MUST NOT 呈现该入口。入口文案 SHALL 取 `label`(非空时),否则回落到界面默认的 "Sign in with SSO" 文案。

#### Scenario: 未启用时端点报告 disabled

- **WHEN** OIDC 未启用,请求 `GET /admin/oidc/config`
- **THEN** 返回 `200`、`{enabled: false}`,且响应不含任何敏感配置字段

#### Scenario: 启用时端点报告 enabled 与文案

- **WHEN** OIDC 启用且配置了 `button_label="Sign in with Google"`,请求 `GET /admin/oidc/config`
- **THEN** 返回 `200`、`{enabled: true, label: "Sign in with Google"}`,且不含 client_secret / issuer 等

#### Scenario: 配置端点不泄漏敏感信息

- **WHEN** OIDC 启用且配置了 client_secret / issuer
- **THEN** `GET /admin/oidc/config` 的响应体只含 `enabled` 与 `label`,不出现任何 secret / issuer / client_id

#### Scenario: 未启用时登录界面不显示 OIDC 入口

- **WHEN** `GET /admin/oidc/config` 返回 `enabled=false`
- **THEN** 登录界面不渲染 OIDC 登录入口(不出现死按钮)

#### Scenario: 启用时登录界面按 label 显示入口

- **WHEN** `enabled=true` 且 `label` 非空
- **THEN** 登录界面渲染 OIDC 登录入口,文案为 `label`;`label` 为空时回落默认 "Sign in with SSO"
