## Context

fleetent 的 MCP 当前 oauth2 仅支持 client_credentials(机器身份),会话按 `(scope, server_id)` 隔离、凭据 per-server 全局,MCP server 永远看到 agent 的机器身份。无法满足"不同用户以各自身份访问同一 MCP server"。

经调研确认的现状约束(本设计据此):

- MCP 全量走官方 `mcp` SDK 的 `ClientSession`;**认证在开会话时绑死**(`call_tool` 无 per-call auth 入口),故 per-user 必须 **per-user 会话**(http)/ **per-user 子进程**(stdio)。
- httpx 的 `auth.auth_flow` **逐请求**被调用 → http 可用"自定义 auth 逐请求读 token"实现刷新透明。
- stdio 标准 server 经 **env 注入**认证,env spawn 后不可变 → per-user 必须每用户一子进程,刷新靠重启。
- `user_id` 已从 IM 入站经 `Principal → ToolContext → call_tool` 全程透传(memory/governance 已在用)。
- 部署两态:**standalone**(agent 自挂 IM + FastAPI,够不到 platform)、**managed**(node 持 IM、解析身份、代理 platform;agent `--no-im`,无 platform 凭据)。两态经注入缝并存(`set_im_identity_resolver` 等先例)。
- 架构契约:agent runtime 禁止 import platform;agent 数据不写 platform 表;长生命周期异步资源 owner-task 同 task enter/exit。

本变更落地**切片 1(共享核 + standalone)**;managed(切片 2)为后续单独变更。

## Goals / Non-Goals

**Goals:**
- per-user OAuth 2.1 Authorization Code 授权,token 按 `(user, agent, server)` 隔离。
- http + stdio 双传输的 per-user 会话/子进程隔离与生命周期。
- 无 token 触发授权链接(PKCE + state 绑 user×agent×server),经 IM 投递。
- 可注入缝 `set_user_token_resolver`,standalone 本地实现,managed 留待切片 2。
- standalone 下 agent 自托管回调 + 本地加密 token 库 + 自刷新。
- 守契约:agent 不 import platform;standalone 无 platform 也能跑;非 per-user 服务行为不变。

**Non-Goals:**
- 切片 2 的 managed 实现(platform 回调/库/refresh/撤销、管理库 `mcp_user_tokens`[Alembic]、node API `POST /nodes/{id}/mcp/oauth-token`、agent→node 同步取 token 通道、跨进程缓存)。
- MCP server 端实现;大文件上传(MCP 不传字节,带外解决,本变更不涉及)。
- 把 OAuth 流程下放到 stdio 子进程内(子进程只消费 token)。

## Decisions

- **D1 token 隔离键 = `(user_id, agent_id, server_id)`**:授权是 agent 级用户委托,agent1≠agent2;token 解析用当前消息 sender 的 principal.user_id(逐消息),不绑会话/频道 → 共享频道里按发送者隔离。备选"按 (user,server) 全局"被否(会跨 agent 串授权)。
- **D2 per-user 会话/子进程,而非共享会话换 token**:SDK 认证绑会话、`call_tool` 无 per-call auth、`Mcp-Session-Id` 有状态 → 共享会话换 token 不可行/不安全。故 http=每用户一 ClientSession、stdio=每用户一子进程;会话键扩 `(scope, server_id, user_id)`,非 per-user 服务键不变(向后兼容)。
- **D3 http 逐请求 auth**:自定义 `httpx.Auth`(绑定该用户),`auth_flow` 每请求读当前 token 设 Bearer → 刷新透明、不重连。迁移到未弃用的 `streamable_http_client(url, http_client=...)`,旧入口留 re-export shim。
- **D4 stdio per-user 子进程池**:每用户一子进程、token 进 env;owner-task 同 task enter/exit,回收发信号不跨 task 拆栈;子进程寿命≤token 有效期,过期/401 重启;空闲超时回收 + 总量/每用户上限(驱逐记日志)+ 孤儿回收 + 关停舱壁化。
- **D5 注入缝 `set_user_token_resolver`**(仿 `set_im_identity_resolver`):模块级 `_resolver=None` + setter + 运行时 `if resolver: ... else 本地回退`。standalone 不注入走本地;managed(切片2)注入。缝不引入反向 import、不持活资源。
- **D6 OAuth 协议逻辑独立模块**:PKCE(S256)、state 生成/校验(一次性+短 TTL)、code 交换、refresh 算法做成与传输/部署无关的纯逻辑模块,standalone 与 managed(切片2)共用。
- **D7 standalone 存储**:agent 侧本地库一张 per-user token 表,经**嵌入式 forward-only 迁移**(对齐 `agent_state_migrations` 范式),密文存 access/refresh/expiry/scope,按三元组键;手写 SQL 走 store 边界、named parameters、不绕 db.py。
- **D8 授权触发复用 degrade/IM 链**:无 token → `call_tool` 返回"需授权"结果(不抛错),standalone 经 agent 自身连接器把授权链接私信给本人(发链接走 DM 不进频道,防他人窃取 state)。

## Risks / Trade-offs

- [stdio 进程数 = 用户数 × server 数,可能耗尽 PID/内存] → 总量+每用户上限、空闲回收、驱逐记日志;文档标注 stdio per-user 偏重,优先 http。
- [owner-task 跨 task 拆栈会崩进程(2026-06-11 事故)] → 回收一律发信号由 owner task 自身收尾;护栏测试禁模块级活资源单例。
- [standalone 下 refresh_token 落 agent 本地] → 单进程单信任域、加密存储;managed 切片再保证 refresh_token 不出 platform。
- [回调 URL 须被用户浏览器可达 + https + redirect_uri 精确匹配] → 文档明确;standalone 适用于浏览器可达 agent 的部署,localhost 仅限同机开发。
- [会话键扩维触碰共享会话表/锁(如 `_call_window_lock`)] → per-user 服务的相关锁降到 `(server,user)` 粒度,避免跨用户串行化;非 per-user 路径保持原状。
- [弃用 API 迁移影响现有 http 服务] → 保留 re-export shim,改动覆盖测试对照 main 基线无新增失败。

## Migration Plan

1. 加注入缝与 OAuth 协议逻辑模块(纯新增,无行为变更)。
2. 会话键扩维 + per-user http/stdio 路径(仅对 per-user oauth 服务生效;旧键/旧行为保留)。
3. standalone 回调 + 本地 token 表(嵌入式迁移,migrate-on-open + 版本闸)。
4. 授权触发 + IM 发链接。
- 回滚:per-user oauth 为新配置项,未配置则全程走旧路径;移除该配置即回退,本地表为附加、不影响既有数据。

## Open Questions

- 无(架构决策已在 brainstorming 锁定;managed 细节留切片 2 单独 propose)。
