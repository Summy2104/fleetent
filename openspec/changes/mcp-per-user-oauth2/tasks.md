# Tasks — mcp-per-user-oauth2(切片 1:共享核 + standalone)

> 每组遵守 TDD Hard Gate:先写测试(见红)→ 再实现(见绿)。单元测试 mock LLM/DB/HTTP;涉及真实 DB/迁移/FastAPI 的放 integration。

## 1. OAuth 协议逻辑模块(纯逻辑,与传输/部署无关)

- [x] 1.1 (test, unit) PKCE:生成 code_verifier/code_challenge(S256)、校验配对;授权 URL 拼装含 response_type/client_id/redirect_uri/scope/state/code_challenge
- [x] 1.2 (test, unit) state:生成不可猜随机 state、绑定 (user_id, agent_id, server_id)+verifier、一次性消费、过期(短 TTL)判定;非法/过期/已消费 state 被拒
- [x] 1.3 (test, unit) code 交换与 refresh 算法:构造 token 端点请求(client_secret_post)、解析 access/refresh/expires;refresh_token grant 刷新;真认证错误 vs 瞬时错误分类
- [x] 1.4 (impl) 实现 OAuth 协议逻辑模块(PKCE / state 管理 / code 交换 / refresh),纯函数 + 可注入时钟,无活资源、无全局可变态
- [x] 1.5 (refactor) 确保协议模块不依赖传输与部署形态,可被 standalone 与未来 managed 共用

## 2. per-user token 存储抽象 + 注入缝

- [x] 2.1 (test, unit) 注入缝 set_user_token_resolver:未注入回退本地;注入后经注入实现;按 (server_id, user_id[, agent_id]) 解析;返回 None 表示无 token
- [x] 2.2 (test, unit) token 存储抽象接口:get/put/delete 按 (user_id, agent_id, server_id) 隔离;不同三元组互不影响
- [x] 2.3 (impl) 定义 token 存储抽象 + set_user_token_resolver 模块级缝(仿 set_im_identity_resolver),standalone 默认本地实现
- [x] 2.4 (test, integration) standalone 本地加密 token 表:嵌入式 forward-only 迁移建表(migrate-on-open + 版本闸)、密文存 access/refresh/expiry/scope、按三元组 CRUD;tmp_path 隔离
- [x] 2.5 (impl) standalone 本地 token store:手写 SQL 走 store 边界、named parameters、不绕 db.py;加密落库

## 3. 会话键扩维(向后兼容)

- [x] 3.1 (test, unit) 会话/注册键:per-user oauth 服务键为 (scope, server_id, user_id);非 per-user 服务键仍为 (scope, server_id);旧调用路径兼容
- [x] 3.2 (test, unit) 工具名投影保持 user-agnostic({server_id}__{tool_name});路由按 principal.user_id 选会话
- [x] 3.3 (impl) 扩展会话注册/查找键含 user 维度(仅 per-user oauth 服务生效),保留旧键路径;相关 per-server 锁(如 _call_window_lock)对 per-user 降到 (server,user) 粒度
- [x] 3.4 (impl) call_tool 路由:按当前 principal.user_id 解析/选择该用户会话(已透传的 user_id)

## 4. http per-user 会话 + 逐请求 Bearer

- [x] 4.1 (test, unit) 自定义 _PerUserBearerAuth:auth_flow 每请求读该用户当前 token 设 Authorization: Bearer;token 变化时下一请求带新 token(透明刷新)
- [x] 4.2 (test, unit) per-user http 会话开启:为每用户建独立 ClientSession,auth 绑定该用户;不同用户独立、同用户复用
- [x] 4.3 (impl) 实现 http per-user 会话 + _PerUserBearerAuth;迁移到 streamable_http_client(url, http_client=带 auth 的 AsyncClient),旧 streamablehttp_client 入口保留 re-export shim
- [x] 4.4 (test, unit) shim 兼容:旧入口仍可用(对照现有 http 服务行为不变)

## 5. stdio per-user 子进程池与生命周期

- [x] 5.1 (test, unit) per-user 子进程键与复用:不同用户不同子进程、同用户复用;token 注入子进程 env(stub spawn)
- [x] 5.2 (test, unit) owner-task 生命周期:每子进程唯一 owner task,enter/exit 同 task;回收经向 owner task 发信号(stop 定向)完成,不跨 task 拆栈
- [x] 5.3 (test, unit) token 过期/401 重启:子进程寿命≤token 有效期,过期或 401 用刷新后 token 重启后重试
- [x] 5.4 (test, unit) 上限与回收:空闲超时回收;总量上限 + 每用户上限,驱逐记日志(非静默);孤儿清理钩子
- [x] 5.5 (impl) 实现 stdio per-user 子进程池(spawn/复用/路由)、owner-task 持有与定向取消、过期重启、空闲回收、上限驱逐、孤儿清理
- [x] 5.6 (test, unit) 关停舱壁化:逐子进程独立超时收尾,单点失败只记日志、不改优雅退出码

## 6. 无 token 触发授权 + 链接投递(standalone)

- [ ] 6.1 (test, unit) 无 token:call_tool 命中无 token 时返回明确「需授权」结果(不抛异常、不卡住,挂 degrade 链);已有有效 token 正常执行
- [ ] 6.2 (test, unit) 授权链接生成:含 PKCE+state(绑 user×agent×server),redirect_uri 精确匹配配置
- [ ] 6.3 (impl) 无 token 分支 + 授权链接生成接线;standalone 经 agent 自身 IM 连接器把链接私信给本人(DM,不进频道)
- [ ] 6.4 (test, unit) 隔离:agent1 授权不被 agent2 使用;共享频道中按发送者 user_id 解析(B 无 token 则 B 触发授权,不复用 A)

## 7. standalone 自挂回调端点

- [ ] 7.1 (test, integration) GET /oauth/callback:合法 state→反查 (user,agent,server)+verifier→code 交换→加密入库→作废 state;非法/过期/已消费 state 被拒、不写 token(FastAPI TestClient)
- [ ] 7.2 (impl) agent FastAPI 挂 /oauth/callback,接 OAuth 协议模块 + 本地 token store;不依赖回调请求登录态(身份由 state 反查)
- [ ] 7.3 (test, integration) access token 过期→agent 用 refresh 自刷新并继续调用,对调用方透明

## 8. 配置

- [x] 8.1 (test, unit) agent.yaml mcp_servers[].auth 解析:oauth2 authorization_code 字段(authorization_endpoint/token_url/client_id/client_secret_env/scope/redirect_path);缺字段报错清晰
- [x] 8.2 (impl) 扩展 McpServerSettings/McpServerConfig 支持 authorization_code 配置;client_credentials 配置与行为不变

## 9. 契约护栏与端到端

- [ ] 9.1 (test, unit) 模块依赖护栏:本变更未新增 agent runtime → platform 反向 import;未新增模块级活资源(AsyncExitStack/连接)单例
- [ ] 9.2 (test, integration) standalone 端到端:用户无 token→收链接→(模拟)授权回调入库→后续以该用户身份调用成功(http 路径)
- [ ] 9.3 (test, integration) 无 platform 基线:platform 表不存在环境下 fleetent agent run 基础对话与无 per-user oauth 配置的 MCP 服务行为不变

## 10. 收尾

- [ ] 10.1 跑受影响层测试(unit + 相关 integration),无新增失败
- [ ] 10.2 make test-pr 全绿(changed-vs-main ruff;层边界检查);改动文件 ruff format + mypy
- [ ] 10.3 自检 owning package / public API / owned tables / config namespace / cross-module deps / shim plan 与 proposal 一致
