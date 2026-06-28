## Context

平台 `mcp_servers` 列(① retire-vault 后未变):`agent_id, server_id, transport, url, auth_type, api_key_env, command, args, env, headers, enabled, created_at`。`materialize._mcp_servers_for_agent`(materialize.py:342)读整行构造 `McpServerSettings(... auth_type, api_key_env, ... headers)`,且 **`auth` 块恒 None**(表无 OAuth 列)。

agent.yaml 侧已具备完整鉴权表达(`config.py`):
- `McpServerSettings`(L235):`auth_type` / `api_key_env` / `headers` / `auth: McpOAuthSettings|None`
- `McpOAuthSettings`(L188):`grant`(client_credentials|authorization_code)/ `token_url` / `client_id` / `client_secret_env` / `scope` / PKCE 字段

explore 校准的边界:
- **静态鉴权** = 平台配置 + secret 走 `agent_secrets`(唯一信源,平台密文 + 平台解密 + node 中转明文 + agent 用 env)。用户**接受**平台是 secret 信源,不要 secret 脱离平台。
- **动态鉴权**(per-user authorization_code)已在 `integrations/mcp/`(oauth_authcode / per_user_tokens / authorization)**完整实现、平台零参与**——本 change 不碰。
- 上次 ② 的错误前提(删 `auth_type` 留 `api_key_env`)会致 managed api-key 静默失效(`auth_type=="api_key"` 是 `_http_headers` 的触发开关);本设计**不删 auth_type**,把鉴权收进结构。

## Goals / Non-Goals

**Goals:**
- `mcp_servers` 鉴权从扁平列 → `auth_type` + `auth_config`(结构化、可扩展)。
- 补 managed 的 `oauth_client_credentials` 静态鉴权入口。
- secret 仍走 `agent_secrets` 唯一信源(auth_config 只存 env 引用名)。
- materialize 翻译为 agent.yaml 现有鉴权字段;agent 侧消费 0 改动。
- 前端按 auth_type 动态表单 + 闭合全局/私有 create 缺口。

**Non-Goals:**
- 不碰动态 per-user 鉴权(已 agent 自管)。
- 不改 secret 架构(平台仍是信源,用户已确认接受)。
- 不碰 MCP 运行时状态/reconnect/doctor/tools(stub,跨解耦边界,独立 change)。
- 不改 `mcp-client` / `mcp-oauth2-auth`(向其对齐,agent.yaml 仍是最终形态)。
- 不碰 model/provider(方向二)、`agent_mcp_servers` 挂载表。

## Decisions

### D1: 结构化用 JSON 列 `auth_config`,不为每类型加扁平列
**选择**:保留 `auth_type`(discriminator),新增 `auth_config` JSON 列;删 `api_key_env`(折叠进 `auth_config.key_env`)。`headers` 保留为连接级。
**理由**:加第 N 种鉴权零表结构改动;符合项目 JSON 列惯例(`kb_connectors.config`、mcp `env/args/headers` 已是 JSON)。auth_config 不需按字段 SQL 查询,JSON 可接受。
**备选**:为 OAuth 加一组扁平列(token_url/client_id/…)——第 N 种又要加列,违背可扩展,否决。

### D2: 鉴权类型 = pydantic discriminated union,单一真相源
**选择**:`auth_type` 做 discriminator,每种类型一个 model 声明字段 + 标 secret env 引用;validation / materialize 翻译 / 前端表单三处共用。oauth 类型复用 `McpOAuthSettings`。
**理由**:类型定义不散落,加类型只动一处 + 前端分支。
**风险点**:auth_config 反序列化按 auth_type 选 model;未知 auth_type 应 validation 拒绝。

### D3: secret 一律 env 引用 + agent_secrets,平台零明文
**选择**:auth_config 的 secret 字段只存 env 名;值走 `agent_secrets`(唯一信源)。沿用现有 api_key_env 模式扩到所有类型。
**理由**:explore 核实 agent_secrets 是全系统 secret 唯一信源,node 仅中转、不持久;为 MCP 另造存储会撕裂信源。

### D4: materialize 翻译 (auth_type, auth_config) → agent.yaml 现有字段
**选择**:`_mcp_servers_for_agent` 读 `auth_type` + 解析 `auth_config`,翻译为 `McpServerSettings` 的 `auth_type` / `api_key_env` / `auth` 块。agent 侧 schema 与 client 消费**不动**。
**理由**:agent.yaml 已能表达全部鉴权;② 只在平台侧做"结构化存储 ↔ agent.yaml 字段"的翻译,agent 侧零改动 = 风险最小。

### D5: headers 留作连接级,不并入鉴权
**选择**:`headers` 保留为 server 连接配置(通用 http 头);鉴权产生的 `Authorization` 由 auth_type 机制生成。
**理由**:避免"headers 既是连接又是鉴权"的二义;减少破坏面(headers 现状不动)。

### D7: 前端动态鉴权表单 = 为每种 auth_type 写明确分支(硬编码),不做通用 schema 端点
**核查发现**:前端 `mcp/page.tsx` 当前 create/edit 表单**完全没有鉴权字段**(只有 id/transport/command/args/url/headers/env);`McpServerRecord`/`McpServerInput` 也无鉴权字段。所以 ② 前端是**从零加整个鉴权配置区块**,不是改现有。
**选择**:前端为每种 `auth_type` 写明确表单分支(硬编码字段集:api_key 1 个 env;oauth 显示 token_url/client_id/scope/client_secret_env),后端 pydantic union 做 validation 权威。**不**加 `GET /admin/mcp/auth-types` schema 端点 + 通用渲染器。
**理由**:静态鉴权类型低频扩展(就 api_key + oauth 两种),通用 schema-driven 表单是 YAGNI;即便后端吐字段,前端仍要为每类型写 i18n/布局/secret 处理,通用化省不掉这些却换来渲染器复杂度;明确分支让每类型 UI 可定制。
**代价 + 缓解**:后端 union 与前端字段表两份定义有漂移风险 → 后端 union 是 validation 权威(前端错传即被拒)+ 加轻量一致性测试。等真要频繁扩展再升级到 schema 端点(届时有稳定模式可抽象)。

### D6: 迁移 109 折叠现有 api_key 行
**选择**:迁移把现有 `(auth_type, api_key_env)` 搬进 `auth_config`(api_key 型 → `{"key_env": <旧值>}`),drop `api_key_env` 列,保留 `auth_type`/`headers`。
**理由**:现有 api-key 型 MCP 不回归——这正是上次"删 auth_type 致静默失效"的正解:不是删,是收进结构。
**风险点**:迁移需正确处理 `auth_type=none` / 空 api_key_env 行(auth_config 为空)。

## Risks / Trade-offs

- **managed api-key 回归** → 迁移折叠 + materialize 翻译必须保持 agent.yaml 鉴权等价;加测试断言"迁移前后 materialize 出的鉴权一致"+ "_http_headers 仍发 Bearer"。
- **越界碰动态鉴权/运行时状态** → 严守 Non-Goal;grep 确认未改 `integrations/mcp/` 动态路径、未改 reconnect/doctor/tools 端点。
- **auth_config schema 漂移** → 类型 union 是单一真相源,前端/materialize/validation 都从它取;加测试覆盖未知 auth_type 拒绝。
- **与方向二同文件** → materialize 只动 `_mcp_servers_for_agent`,不碰 `_models_from_overrides`/`_target_from_model_override`。
- **迁移号撞号** → 取 109(chain 在 108 后);merge 后 `uv run alembic heads` 确认单 head,撞号则重链。

## Migration Plan

1. 定义鉴权类型 union（平台侧 auth-config models，oauth 复用 `McpOAuthSettings`）。
2. Alembic 迁移 109：`mcp_servers` 新增 `auth_config`(JSON)、把现有 api_key 行折叠进去、drop `api_key_env`；保留 `auth_type`/`headers`。
3. `mcp_server_store`：列定义 / add / edit 改为 `auth_type` + `auth_config`。
4. `materialize._mcp_servers_for_agent`：读 auth_type + auth_config，翻译为 `McpServerSettings` 鉴权字段（含 oauth `auth` 块）。
5. admin API（`connector_admin_api.py` MCP 端点）：create/edit 入参改结构化 auth_config（按 auth_type）。
6. 前端 `features/mcp/`：按 auth_type 动态表单 + create scope（agent_id）。
7. 测试：迁移前后鉴权等价、managed oauth 可配、api-key 不回归、动态鉴权未受影响。
- **回滚**：迁移 109 反向把 auth_config.key_env 还原回 api_key_env 列（api_key 型可逆；oauth 型为新增能力、回滚即丢配置，可接受）。

## Open Questions

- 鉴权类型 union 放平台侧新模块还是直接复用/扩展 `config.py` 的 model——apply 时按"单一真相源 + agent 侧不被平台逻辑污染"权衡(平台侧 model 不应被 agent runtime import)。
- MCP 运行时状态(假 status/tool_count/reconnect/doctor)仍是独立待办,随本 change 之后单列。
- `data-model.md` §3.2 `mcp_servers` 列说明在 archive 阶段同步(auth_config 替 api_key_env)。
