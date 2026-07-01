## MODIFIED Requirements

### Requirement: platform 公开回调完成 code→token 并存管理库

platform SHALL 暴露公开路由 `GET /oauth/callback`,以回调带回的 `state` 反查 pending-auth(MUST NOT 依赖回调请求的登录态),用 D6 纯逻辑以 `code` + `code_verifier` 向 token 端点交换 access+refresh token,并 SHALL 把 token 密文存入管理库 `mcp_user_tokens`,按 `(user_id, agent_id, server_id)` 三元组键隔离。交换所用 client_secret SHALL 经 `agent_secrets` 由 `client_secret_env` 解析,MUST NOT 入 `mcp_user_tokens` 或注册表。

client_secret 解析 SHALL 接受运行时三元组中以 agent **名字**形式出现的 agent 身份:注入的解析器 SHALL 把 agent 名字经注册表映射到其数字 id 后再查 `agent_secrets` 的 per-agent 作用域(数字身份直接采用),并 SHALL 在 per-agent 作用域无值时回退到全局(`agent_id IS NULL`)作用域。该 name→id 映射 SHALL 位于组合根注入的解析器内,`connector_management` face MUST NOT 因此 import `agent_lifecycle`/`agent_store`。

#### Scenario: 回调以 state 反查并换 token 入管理库
- **WHEN** 用户在浏览器完成授权,授权服务器重定向回 platform `/oauth/callback?code&state`
- **THEN** platform 校验 state → 反查三元组与 code_verifier → 换取 access+refresh token → 密文存管理库 `mcp_user_tokens`(三元组键);state 随即作废

#### Scenario: 三元组隔离
- **WHEN** 同一用户对两个不同 agent 授权同一 MCP server
- **THEN** 两条 token 记录按各自三元组独立存储,互不可见、互不复用

#### Scenario: 以 agent 名字命中 per-agent client_secret
- **WHEN** pending 记录的 agent 身份是 agent 名字(非数字),且该 agent 在 `agent_secrets` 配有对应 `client_secret_env` 的 per-agent 密文值
- **THEN** 解析器把名字映射到该 agent 的数字 id,取到 per-agent client_secret 完成交换(不落空、不误退全局)

#### Scenario: per-agent 缺失时回退全局
- **WHEN** 以 agent 名字解析 client_secret,但该 agent 无 per-agent 值、而全局(`agent_id IS NULL`)作用域配有该 env
- **THEN** 解析器回退到全局值完成交换

#### Scenario: 未知 agent 名字解析为空
- **WHEN** agent 名字在注册表中不存在且全局作用域也无该 env
- **THEN** 解析器返回空 client_secret(PKCE 公共客户端语义不变),不抛错、不泄露
