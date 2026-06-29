## Context

切片 1 已落地 per-user OAuth 2.1 authorization_code 的**共享核 + standalone 实现**:`(user_id, agent_id, server_id)` 三元组隔离、http per-user 会话、stdio per-user 子进程、PKCE/state/code交换/refresh 的**纯逻辑模块(D6)**、注入缝 `set_user_token_resolver`、`UserToken`/`UserTokenStore` 抽象,以及 standalone 的自托管回调 + 本地加密 token 库。

managed 部署形态(见 `mcp-per-user-oauth` 切片 1 spec 与 AGENTS.md):node 持 IM、解析身份、代理 platform;agent 以 `--no-im` 运行,**无 platform 凭据、不持公开 ingress、禁止 import platform**。切片 1 把 managed 的 token 来源留给注入缝,本切片补齐。

raw34 的 `slim-mcp-to-agent-auth`(2026-06-29,迁移 109)已把 MCP 静态鉴权重构为 `auth_type`(discriminator)+ `auth_config`(JSON)的判别联合,schema 在 `platform/connector_management/mcp_auth.py`,目前含 `none`/`api_key`/`oauth_client_credentials` 三型,**无 authorization_code**。

约束:agent runtime MUST NOT import platform;agent 数据不写 platform 表;长生命周期异步资源 owner-task 同 task enter/exit;手写 SQL 走 store 边界、named parameters、不绕 db.py;管理表仅由 Alembic 维护。

## Goals / Non-Goals

**Goals:**
- managed 下 per-user OAuth authorization_code 完整 happy-path:发起 → platform 回调换 token → 管理库存储 → agent 经 node 同步取短期 access token。
- agent↔platform **同一套配置 schema 与 OAuth 协议逻辑**;managed 与 standalone 仅在"谁持 token / 谁跑回调"分叉。
- 守解耦:agent 不 import platform;**无 platform 时 standalone 照常跑**(注入缝不注入即回落本地)。
- refresh_token 与 client_secret **永不出 platform**。

**Non-Goals:**
- 撤销(revocation):后续单独切片。
- standalone 行为变更:切片 1 路径语义不变(仅随 schema 提取跟着改 import)。
- MCP server 端实现;stdio/http 隔离机制(切片 1 已建,复用)。

## Decisions

- **DM1 鉴权 schema 提取到中立模块 + 新增 authorization_code 类型**:把 `auth_type`+`auth_config` 判别联合从 `platform/connector_management/mcp_auth.py` 移到 **agent 与 platform 都能 import 的中立位置**(随 agent 侧既有 `config.py`/`agent_config` 范式,不在 platform 包内),新增 `OAuthAuthorizationCodeMcpAuthConfig`(`auth_type="oauth_authorization_code"`,字段 authorization_endpoint/token_url/client_id/client_secret_env/scope/redirect_path,`client_secret_env` 标为 secret env 引用)。原 `mcp_auth.py` 留 **re-export shim** 使 raw34 既有 import 不破。`client_id` 经 `_resolve_env_ref` 支持 `${ENV}`。**备选**:agent/platform 各持镜像 schema(否:双轨易漂移,违"同一套 schema")。

- **DM2 授权发起留 agent,与 standalone 同逻辑**:`call_tool` 无 token → agent 用 D6 建授权 URL(PKCE + state),仅 `redirect_uri` 在 managed 指向 platform 回调;经现有 IM 链(managed = node IM / directed-reach)把链接 DM 给用户本人。**备选**:platform 发起(否:违"授权逻辑同 standalone",且 agent 已持发起所需的全部上下文)。

- **DM3 platform 持回调 + 换/刷新/存,经管理库**:platform 公开 `GET /oauth/callback`(on-prem 控制面,用户浏览器可达),按 state 反查 pending-auth → 用 D6 做 code→token → 存管理库 `mcp_user_tokens`(密文,三元组键)。refresh 在 platform 用 refresh_token 透明完成。**备选**:node 持回调(否:node 非公开可达、按契约不引 DB)。

- **DM4 pending-auth 经 node 登记**:agent 建授权 URL 前,把 `state→(code_verifier, user×agent×server, token_url/client_id/client_secret_env)` 经 node 转发到 platform `POST /nodes/{id}/mcp/oauth-pending` 存(短 TTL、一次性),供回调时完成交换。code_verifier 必须到达 platform(由 platform 做交换),经此通道一次性下发,**不落 agent 持久层**。

- **DM5 agent→node 同步 loopback 通道**:managed 下 agent 需在 call_tool 当刻同步取 token,而既有 agent→node 仅异步队列(directed-reach),喂不了。故新增一条 **本机 loopback 同步小通道**:node 监听本地端点,spawn agent 时经 env(如 `FLEETENT_NODE_LOOPBACK_URL` + 短凭据)注入;node 收到后持 service key 转发 platform `/nodes/{id}/mcp/oauth-pending|oauth-token`。通道**仅本机、仅这两类请求**;不引入 agent→platform 直连、不让 agent 持 platform 地址/凭据。**备选**:复用异步队列(否:首次每工具调用掉一回合);agent 直连 platform(否:违解耦)。

- **DM6 managed resolver + agent 进程内短 TTL 缓存**:managed 启动注入 `set_user_token_resolver`,resolver 走 DM5 通道取 token;agent 进程内按三元组短 TTL 缓存 access token(TTL~临近过期),未命中/过期/MCP 401 → 经通道重取,platform 端透明 refresh。resolver 注入侧返回的 `UserToken` **只含 access_token**(refresh_token=None),保证 refresh_token 不出 platform。**注意**:注入缝签名为同步 `Callable[(server_id,user_id,agent_id|None)] -> UserToken|None`;managed resolver 内的 node loopback 调用在同步上下文执行(必要时 `anyio.from_thread`/阻塞本机调用),不在 http auth_flow 热路径做阻塞网络。

- **DM7 token 复用切片 1 抽象**:管理库 store 实现复用 `UserToken` 数据结构与三元组语义;platform 侧为独立 store(Alembic 表),与 agent 本地 store(切片 1 嵌入式迁移)并行,经注入缝二选一(managed 注入则不碰本地 store)。

## Risks / Trade-offs

- [提取 raw34 刚落的 schema 文件,可能与其在途改动冲突] → 留 re-export shim 保持其 import 不破;只移动 + 扩展,不改其 `none`/`api_key`/`oauth_client_credentials` 语义;改动对照 main 基线无新增失败。
- [同步注入缝里做 node 网络调用,阻塞 async loop] → resolver 在会话/子进程构建处取并缓存,不在 per-request 热路径阻塞;loopback 为本机低延迟;短 TTL 缓存摊薄频次。
- [agent→node 新增同步出站,扩大 agent 出站面] → 通道仅本机 loopback、仅 oauth-pending/oauth-token 两类、需 spawn 注入的短凭据;agent 仍不持 platform 地址/凭据、不 import platform。
- [code_verifier 经通道下发到 platform] → 一次性、短 TTL、随 state 作废;通道本机 + 凭据校验;refresh_token/client_secret 仍不出 platform。
- [回调 redirect_uri 须用户浏览器可达 + https + 精确匹配] → on-prem platform 控制面为公开 https 落点;文档明确 redirect_path 配置与预注册匹配要求。
- [managed 与 standalone 双回调形状若漂移] → 回调处理与 code→token 走同一 D6 纯逻辑;两态只在存储后端(管理库 vs 本地库)与触发上下文不同。

## Migration Plan

1. 提取鉴权 schema 到中立模块 + 新增 `oauth_authorization_code` 类型 + `mcp_auth.py` re-export shim(纯重构 + 扩展,既有行为不变,覆盖测试对照 main 无新增失败)。
2. 管理库 `mcp_user_tokens` 表 Alembic 迁移(110+)+ platform token store + pending-auth 短 TTL 存储。
3. platform `GET /oauth/callback` + `POST /nodes/{id}/mcp/oauth-pending` + `POST /nodes/{id}/mcp/oauth-token`(换/刷新复用 D6)。
4. node agent→node loopback 同步通道 + 转发 + spawn 注入 env。
5. agent managed 注入 resolver(经通道)+ 进程内短 TTL 缓存 + 401/过期重取;授权发起 redirect_uri managed 指向 platform。
- **回滚**:per-user oauth authorization_code 为新配置;managed 未注入 resolver 即回落切片 1 本地路径;移除配置即全程走旧路径;`mcp_user_tokens` 为附加表,不影响既有数据。

## Open Questions

- 无(架构在 brainstorming 锁定;实现细节如 loopback 凭据形态、缓存 TTL 数值在 apply 阶段按既有范式定:loopback 凭据复用 node 注入 secret 范式,缓存 TTL 取 access token expiry 前留余量)。
