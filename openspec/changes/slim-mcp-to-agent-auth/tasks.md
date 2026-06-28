## 1. 鉴权类型 schema(discriminated union · 测试先行)

- [ ] 1.1 写测试:auth_type union 按 discriminator 选 model;`api_key` 要 `key_env`、`oauth_client_credentials` 复用 McpOAuthSettings 字段;缺必需字段 / 未知 auth_type validation 拒绝(`tests/unit`,见红)
- [ ] 1.2 实现鉴权类型 union(平台侧 model;oauth 复用 `config.py` 的 `McpOAuthSettings`;标注哪些字段是 secret env 引用)→ 跑 1.1 见绿;**平台侧 model 不得被 agent runtime import**

## 2. Alembic 迁移 109(结构化 + 折叠 api_key · 测试先行)

- [ ] 2.1 写迁移测试:升级 109 后 `mcp_servers` 有 `auth_config`、无 `api_key_env`、仍有 `auth_type`/`headers`;现有 api_key 行的旧 `api_key_env` 值已折叠进 `auth_config.key_env`;`auth_type=none`/空值行 auth_config 为空(`tests/integration`,见红)
- [ ] 2.2 实现迁移 `109_mcp_auth_config.py`:新增 `auth_config` JSON、折叠现有 api_key 行、drop `api_key_env`(chain 在 108 后)→ 跑 2.1 见绿

## 3. store 改结构化鉴权(测试先行)

- [ ] 3.1 写测试:`mcp_server_store` add/edit/列定义用 `auth_type` + `auth_config`(无 `api_key_env`);secret 值不入库,只存 env 引用名(`tests/integration`,见红)
- [ ] 3.2 改 `mcp_server_store`:COLUMNS / add_mcp_server / edit 用 `auth_type` + `auth_config` → 跑 3.1 见绿

## 4. materialize 翻译(测试先行 · 守 api-key 不回归)

- [ ] 4.1 写测试:`_mcp_servers_for_agent` 把 (auth_type, auth_config) 翻译为 `McpServerSettings` —— api_key 型 → `auth_type=api_key`+`api_key_env`;oauth 型 → `auth` 块(grant/token_url/client_id/scope/client_secret_env);**断言迁移前后某 api_key 型 server 的 materialize 鉴权等价**(`tests/integration`,见红)
- [ ] 4.2 改 `materialize._mcp_servers_for_agent`:读 auth_type + 解析 auth_config,翻译鉴权字段;**不碰** `_models_from_overrides`/`_target_from_model_override`、agent 侧 schema → 跑 4.1 见绿
- [ ] 4.3 写测试 + 验证:`integrations/mcp/client.py` 的 `_http_headers` 对翻译后的 api_key 型仍发 `Authorization: Bearer`(守上次"静默失效"坑)

## 5. admin API 后端(MCP 端点收结构化鉴权)

- [ ] 5.1 写测试:create/edit MCP 端点收结构化 `auth_config`(经 auth_type union 校验)、不收扁平 `api_key_env`、不收 secret 明文;create 传 `agent_id` 建全局/私有(后端 `tests/integration`,见红)
- [ ] 5.2 改 `connector_admin_api.py` MCP 端点:create/edit 鉴权入参改 `auth_config`(经 union 校验)。**只动 MCP 端点,不碰 ① 已清空的 OAuth 区域** → 跑 5.1 见绿

## 6. 前端(从零加鉴权 UI · 现状表单完全无鉴权字段)

> 核查现状:`mcp/page.tsx` 表单只有 id/transport/command/args/url/headers/env;`McpServerRecord`/`Input` 无鉴权字段、无 auth_type。本组是**新增**整个鉴权配置区块(D7:为每种 auth_type 写明确分支,不做通用 schema 端点)。

- [ ] 6.1 写前端测试(vitest,见红):`McpServerRecord`/`McpServerInput` 含 `auth_type`+`auth_config`;create/edit 表单按 auth_type 渲染 **api_key 分支**(1 个 env-name)/ **oauth 分支**(token_url/client_id/scope/client_secret-env-name);只收 env 引用名不收 secret 明文;create 含 scope(agent_id)选择
- [ ] 6.2 改 `connectors/api.ts`:`McpServerRecord`/`McpServerInput` 加 `auth_type` + `auth_config` 结构(移除残留 `api_key_env` 若有);create/edit mutation 传 `auth_config`
- [ ] 6.3 改 `mcp/page.tsx`:**新增鉴权区块** —— `auth_type` 选择 + 为 api_key / oauth_client_credentials **各写明确表单分支**(D7 硬编码字段);**新增 scope 选择**(全局/某 agent)→ 请求传 `agent_id`
- [ ] 6.4 `i18n/messages.ts`:新增鉴权相关文案(auth_type 标签 + 各类型字段标签;现状零鉴权 key)
- [ ] 6.5 加轻量一致性测试:后端 union 字段集与前端表单字段对齐(防 D7 两份定义漂移)→ 跑 6.1 见绿

## 7. 守界与验证

- [ ] 7.1 grep 确认未碰:动态 per-user 鉴权(`integrations/mcp/` 的 oauth_authcode/per_user_tokens/authorization)、MCP 运行时状态/reconnect/doctor 与前端假 `status`/`tool_count` 列、`agent_mcp_servers` 挂载表、model/provider、secret 架构
- [ ] 7.2 managed 端到端烟测:配一个 oauth_client_credentials 型 MCP(client_secret 经 agent_secrets)→ materialize → agent.yaml 含 auth 块 → 连接;再配一个 api_key 型确认不回归
- [ ] 7.3 跑 `make test-pr` + `make test-unit-ci`(覆盖率 76%) + `make test-integration-ci` + `cd frontend && yarn test` 全绿(对照 main 基线无新增失败)
- [ ] 7.4 收尾:`uv run alembic heads` 确认单 head(109);`data-model.md` §3.2 `mcp_servers` 列说明同步(归 archive 阶段)
