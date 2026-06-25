## ADDED Requirements

### Requirement: 支持 authorization_code(用户委托)grant

在现有 `client_credentials`(机器身份)之外,MCP 的 oauth2 认证 SHALL 支持 `authorization_code`(用户委托)grant,使取得的 token 代表**具体用户**而非服务主体。配置 SHALL 经 `agent.yaml` 的 `mcp_servers[].auth` 声明 authorization_code 所需字段(authorization_endpoint、token_url、client_id、client_secret_env、scope、redirect_path)。authorization_code 路径 MUST 使用 PKCE(S256);token 端点 MUST 为客户可自托管的授权服务器,MUST NOT 依赖云托管专有身份服务。现有 client_credentials 行为 MUST 保持不变。

#### Scenario: 配置 authorization_code 的服务走用户委托授权
- **WHEN** 一个 MCP 服务配置 `auth_type: "oauth2"` 且 grant 为 `authorization_code`
- **THEN** 系统走用户委托授权流程(per-user 授权链接 + code 交换),取得的 token 代表发起授权的用户

#### Scenario: client_credentials 行为不变
- **WHEN** 一个 MCP 服务仍配置 client_credentials grant
- **THEN** 其取 token 与 Bearer 注入行为与现状完全一致,不受 authorization_code 支持影响

### Requirement: per-user token 解析注入缝

oauth2 认证 SHALL 暴露一个模块级可注入的 per-user token resolver 缝 `set_user_token_resolver(resolver)`,供 authorization_code 路径按用户解析 token。未注入时回退本地(standalone)实现;注入后(managed)经注入实现解析。该缝 MUST NOT 使 agent runtime 反向 import platform,MUST NOT 以模块级可变全局持有活资源(连接/会话)。

#### Scenario: 注入缝按用户解析 token
- **WHEN** authorization_code 服务需要某用户的 token
- **THEN** 经 `set_user_token_resolver` 注入的(或本地回退的)resolver 按 `(server_id, user_id)` 解析 token

#### Scenario: 缝不破坏模块依赖契约
- **WHEN** 校验模块依赖护栏
- **THEN** 该缝不引入 agent runtime → platform 的反向 import,也无新增模块级活资源单例
