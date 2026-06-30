## ADDED Requirements

### Requirement: auth_type 判别枚举不被 inline-secret 守卫误报

`auth_type` 是 MCP server 鉴权配置的**判别枚举（discriminator）**，取值受约束（`none` / `api_key` / `oauth_client_credentials` / `oauth_authorization_code` / `api_key_per_user`），**永不承载 secret**。agent.yaml 加载时的 inline-secret 守卫（拒绝内联明文密钥）SHALL NOT 将 `auth_type` 的值当作候选 inline secret 扫描/报错——即使该枚举值被通用"像密钥"启发式误判。由此，经连接器物化出顶层 `auth_type`（如 `oauth_authorization_code` / `oauth_client_credentials`）的 agent SHALL 能正常加载并启动，不因判别枚举被 boot 守卫拦截。对真正承载 secret 的字段（secret 的 `*_env` 引用名以外的内联明文）扫描行为 MUST 保持不变。

#### Scenario: 连接器物化的 oauth_authorization_code agent 正常加载

- **WHEN** 一个 MCP server 经连接器物化出顶层 `auth_type: oauth_authorization_code` 进 agent.yaml，agent 加载该配置
- **THEN** inline-secret 守卫不因 `auth_type` 的枚举值报错，agent 正常加载/启动

#### Scenario: 真正的内联明文 secret 仍被拦截

- **WHEN** agent.yaml 的某 MCP server 字段（非 `*_env` 引用、非结构判别字段）内联了像密钥的明文值
- **THEN** inline-secret 守卫仍报错，要求改用环境变量引用（扫描行为不被本豁免削弱）
