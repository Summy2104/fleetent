## 1. 鉴权 schema:per-user api-key variant + 配置

- [x] 1.1 写测试(红):`mcp_auth_models` 解析 `api_key_per_user`(header_style 默认 bearer、credential_input 默认 form);无静态 key/key_env;非法值被拒;静态 `api_key` 不回归
- [x] 1.2 实现(绿):中立 `mcp_auth_models` 新增 `ApiKeyPerUserMcpAuthConfig` variant(header_style / credential_input);shim re-export;判别联合纳入
- [x] 1.3 写测试(红)+ 实现(绿):materialize 把 `api_key_per_user` 翻译为 agent.yaml per-user api-key 表示(header_style/credential_input);api_key/oauth 翻译不回归

## 2. 类型感知存储 + per-request 注入(复用三元组)

- [x] 2.1 写测试(红):两侧 `mcp_user_tokens` 加 `credential_kind`(agent 内嵌迁移 v-next + platform Alembic 111);migrate head 后列存在且既有行回填 `oauth`;down 可回滚
- [x] 2.2 实现(绿):两侧迁移加 `credential_kind`(默认/回填 `oauth`);store put/get 带 kind(`static` 只存密钥密文、OAuth 列 NULL);platform `fetch_access_token`/refresh 路径 MUST 跳过 `static`(不刷新静态凭据)
- [x] 2.3 写测试(红):per-user api-key 经 `resolve_user_token` 统一入口取用;http 注入**按 server `header_style`** 走 `Authorization: Bearer` 或 `X-API-Key`;stdio env 注入;无 key→注入跳过(触发 degrade)
- [x] 2.4 实现(绿):client.py 识别 per-user api-key server(`_is_per_user_apikey`),按 `header_style` 注入(复用 `_PerUserBearerAuth` / 新增 X-API-Key per-user auth)+ stdio env;凭据以 `kind=static` 存三元组
- [ ] 2.5 写测试(红)+ 实现(绿):无 key 调用返回明确「需凭据」degrade 结果(不抛错/不卡),按 credential_input 触发提交

## 3. 安全表单提交(模式1,默认):state + 端点 + standalone

- [ ] 3.1 写测试(红):一次性短 TTL state 绑定三元组(issue/consume,过期/二次消费被拒);凭 state 反查身份不依赖登录态
- [ ] 3.2 实现(绿):凭据 pending/state 存储(standalone 本地 / 复用 OAuth pending 同款结构)
- [ ] 3.3 写测试(红):standalone agent `GET /mcp/credential?state`(渲染表单)+ `POST /mcp/credential`(state 校验→密文存本地三元组);key 不进对话;非法 state 拒
- [ ] 3.4 实现(绿):standalone 自托管凭据表单 + 提交端点 + 本地加密存储
- [ ] 3.5 写测试(红)+ 实现(绿):无 key 触发经 DM 投递凭据提交链接(复用 set_authorization_link_deliverer / directed-reach;链接指向表单)

## 4. managed 提交(模式1):platform 端点 + node loopback

- [ ] 4.1 写测试(红):platform `GET/POST /mcp/credential`(state 反查→密文存管理库三元组);非法/过期 state 拒;明文 key 不出 platform
- [ ] 4.2 实现(绿):platform 凭据提交端点 + 管理库存储(复用 mcp_user_token_store)
- [ ] 4.3 写测试(红)+ 实现(绿):agent 经 node loopback 登记凭据 pending(复用/同构 oauth-pending);node 不 import platform、仅转发

## 5. 对话内工具提交(模式2,opt-in,限 DM)

- [ ] 5.1 写测试(红):`set_mcp_credential` 仅当 server credential_input∈{tool,both} 可见;DM 上下文受理存三元组;频道内拒绝并引导;form-only 时不可用
- [ ] 5.2 实现(绿):内置 `set_mcp_credential` 工具(DM-gated、按 credential_input 门控、写 per-user 三元组);工具入参 trace 脱敏(复用 tool-arg-secret-redaction)

## 6. 集成闭环 + 守护 + 收尾

- [ ] 6.1 写集成测试(红→绿):per-user api-key happy-path 端到端——无 key→需凭据→表单提交存库→后续调用按 header_style 注入成功(standalone)
- [ ] 6.2 写集成测试(红→绿):managed happy-path(经 node→platform 端点提交 + 取用);契约守护——agent 不 import platform、明文 key 不出对话/不出 platform;静态 api_key 不回归
- [ ] 6.3 跑 `make test-pr` + `make test-integration-ci`,对照 main 基线无新增失败;模块/层/plane 守护通过
- [ ] 6.4 openspec validate 通过;归档前确认所有 checkbox 为 [x]
