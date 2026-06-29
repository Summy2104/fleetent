## 1. 鉴权 schema 提取到中立模块 + authorization_code 类型

- [x] 1.1 写测试(红):中立模块导出 `auth_type` 判别联合含 `oauth_authorization_code`;agent 侧 import 该 schema 不触发 platform import(模块边界守护);`client_id` env 引用解析;非法 auth_config 被拒
- [x] 1.2 实现(绿):把 `auth_type`+`auth_config` 判别联合从 `platform/connector_management/mcp_auth.py` 移到中立模块,新增 `OAuthAuthorizationCodeMcpAuthConfig`(authorization_endpoint/token_url/client_id/client_secret_env/scope/redirect_path,client_id 经 `_resolve_env_ref`)
- [x] 1.3 实现(绿):`platform/connector_management/mcp_auth.py` 改为 re-export shim;跑模块边界检查 `scripts/check_module_boundaries.py` 确认 agent 侧零 platform import
- [x] 1.4 写测试(红)+ 实现(绿):materialize 把 `oauth_authorization_code` 翻译为 agent.yaml authorization_code `auth` 块;api_key / client_credentials 翻译不回归

## 2. 管理库 mcp_user_tokens + platform token store + pending-auth 存储

- [x] 2.1 写测试(红):Alembic 迁移(110+)建 `mcp_user_tokens`(三元组键),migrate head 后表存在;down 可回滚
- [x] 2.2 实现(绿):新增 Alembic 迁移建 `mcp_user_tokens` 表
- [x] 2.3 写测试(红):token store put/get/delete 按 `(user,agent,server)` 三元组隔离,access/refresh/expiry/scope 密文存,named parameters 经 store 边界;refresh_token 不经读接口外泄
- [x] 2.4 实现(绿):platform 侧 `mcp_user_tokens` store(手写 SQL、named params、密文)
- [x] 2.5 写测试(红)+ 实现(绿):pending-auth 短 TTL 一次性存储(state→code_verifier/三元组/token端点/client),过期或二次消费被拒

## 3. platform 回调 + node↔platform 端点 + 透明刷新

- [x] 3.1 写测试(红):`GET /oauth/callback` 以 state 反查 pending → 用 D6 换 token → 存管理库 → state 作废;非法/过期 state 被拒;client_secret 经 agent_secrets 解析不入表
- [x] 3.2 实现(绿):platform `GET /oauth/callback` 路由(复用 slice-1 D6 纯逻辑做 code→token)
- [x] 3.3 写测试(红):`POST /nodes/{id}/mcp/oauth-pending` 鉴 node service key 后登记 pending;非 node 调用被拒
- [x] 3.4 实现(绿):`POST /nodes/{id}/mcp/oauth-pending` 端点
- [x] 3.5 写测试(红):`POST /nodes/{id}/mcp/oauth-token` 返回有效 access token,过期且有 refresh 时透明刷新后返回,返回体不含 refresh_token;非 node 调用被拒
- [x] 3.6 实现(绿):`POST /nodes/{id}/mcp/oauth-token` 端点(复用 D6 refresh)

## 4. node agent→node 同步 loopback 通道

- [x] 4.1 写测试(红):node loopback 通道收 oauth-pending/oauth-token 请求 → 持 service key 转发对应 platform 端点 → 同步返回;缺/错凭据被拒;非这两类请求被拒
- [x] 4.2 实现(绿):node loopback 同步通道 + 转发到 platform 端点(node 持 service key)
- [x] 4.3 写测试(红)+ 实现(绿):node spawn agent 时经 env 注入 loopback 通道地址 + 短凭据

## 5. agent managed resolver + 缓存 + 重取 + redirect 落点

- [x] 5.1 写测试(红):managed 注入的 resolver 经 loopback 通道取 token,返回 `UserToken` 仅含 access_token(refresh_token=None)
- [x] 5.2 实现(绿):managed 启动注入 `set_user_token_resolver`(经 loopback 通道)
- [x] 5.3 写测试(红):进程内短 TTL 缓存命中不打 node;过期 / MCP 401 触发经通道重取;未注入 resolver 回落本地库(standalone 不变)
- [x] 5.4 实现(绿):agent 进程内短 TTL 缓存 + 过期/401 重取
- [x] 5.5 写测试(红)+ 实现(绿):managed 下授权发起 `redirect_uri` 指向 platform 回调,发链接前经通道登记 pending-auth(standalone 仍指向 agent 自身回调,逻辑同源)

## 6. 集成闭环 + 守护 + 收尾

- [x] 6.1 写集成测试(红→绿):managed happy-path 端到端(无 token→需授权→回调换 token 入管理库→后续调用经 node 取 token→成功),mock 授权服务器 token 端点
- [x] 6.2 写测试(红→绿):无 platform 时 standalone per-user OAuth 仍跑通(注入缝不注入,回落本地);契约守护——agent 不 import platform、refresh_token/client_secret 不出 platform
- [x] 6.3 跑 `make test-pr` + `make test-integration-ci`,对照 main 基线无新增失败;模块边界 + 层边界检查通过
- [x] 6.4 openspec validate 通过;归档前确认所有 checkbox 为 [x]
