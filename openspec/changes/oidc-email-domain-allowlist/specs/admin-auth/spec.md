## ADDED Requirements

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
