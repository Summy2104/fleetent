## Context

托管 agent 当前零入站端口(`node/backend.py` Popen 不带 `--port`;agent `/chat`·`/ws` 仅在给 `--port` 时起,见 `agent_app`)。IM 走出站,不需入站。运维要对话/调试托管 agent 却无路可走(prune 已删 admin 内嵌 chat)。已有资产可复用:agent 侧 `/ws` 网关(`tui-gateway`)+ `FLEETENT_TUI_TOKEN` 认证(`tui-agent-token-auth`);平台 `placement_store`(agent→node);node 既有 node-key 认证(`node-desired-state-api`)。node 当前**无任何 HTTP**,forwarder 是新建。

## Goals / Non-Goals

**Goals:** 运维能从平台对话/调试任意托管 agent;三层职责清晰(平台门面 / node 管道 / agent 内网 gateway);reach 抽象化,(i) 直连先行、(ii) 反向通道可后替;托管 agent 的 TUI token 自动供给(B2)。
**Non-Goals:** 不做运维聊天前端页(后续);不做通用 webhook 路由(后续);不实现 (ii) 反向通道(仅留接口);不破坏 agent↔platform 解耦与 desired-state 无明文密钥契约;不引入 schema 迁移(优先)。

## Decisions

**D1 · 三层 + reach (i) 直连,藏在 transport seam 后。**
平台门面收运维请求 → 按 placement 选 node → `AgentTransport` 接口 → **DirectHttp** 实现拨向 node forwarder。接口契约**支持流式**(请求 → 流式响应),使 (ii) node 反向出站通道日后只换实现、不动门面/路由/agent gateway。备选:平台直拨 agent 端口——否决,会让 agent 不再 localhost-only 且绕过 node 管道角色。

**D2 · Node 当管道,新建仅内网 forwarder。**
node 起一个**仅绑内网**的小 HTTP forwarder,受 **node key** 认证(复用既有 node 鉴权)。它知道本机每个 agent 的 localhost 端口(B3 登记),把平台请求转给目标 agent,并注入该 agent 的 `FLEETENT_TUI_TOKEN`。agent 保持 **localhost-only**,不直接对外。

**D3 · 认证链:逐跳、平台不持 agent token。**
运维 →(admin Session,平台门面校验)→ 平台 →(node key)→ node forwarder →(agent `FLEETENT_TUI_TOKEN`,**node 注入**)→ agent `/ws`。node 持有 token(来自它写的 `.env`),平台只认 node、不接触 agent token——最小权限、职责清晰。

**D4 · B3 端口分配 + 登记,优先无迁移。**
node 给每个被拉起的 agent 分配一个内网端口(可用范围内取空闲),带 `--port` 起,并登记(进程内映射即可满足 forwarder 路由;若要平台侧可见,复用 `node_agent_status` 现有字段或上报,不轻易加列/迁移)。

**D5 · B2 在 materialize 供给 token,沿用 secret 路径、不进 desired-state 明文。**
`agent init` 已会生成 `FLEETENT_TUI_TOKEN`,但托管 agent 不走 init。故 `materialize._seed_env` 为托管 agent 供给该 token(缺则生成 `ma-<64hex>`,有则保留),经既有 secret 下发路径到 node 的 `.env`——**不写进 desired-state 明文 config**(守 `node-secret-injection` 契约)。

## Risks / Trade-offs

- **[平台进入数据面,担心主权]** → 平台只**转发**对话、不落 agent 数据;会话/记忆仍 agent 侧。on-prem 全内网。
- **[node 首开入站口]** → forwarder 仅绑内网 + node key 认证;(i) 的代价就是 node 一个内网口,(ii) 可消除——seam 已留好切换口。
- **[流式回传复杂度]** → 契约从第一天就按"请求→流式响应"设计;(i) DirectHttp 直接代理 WS/SSE,(ii) 日后实现同契约。
- **[与并行前端域撞车]** → 本切片纯后端(server.py/node/agent_app/materialize),与 `frontend/` 的 3 个域零重叠;B2 与已并 A 同文件不同函数。
- **[改 agent_app 影响直跑基线]** → gateway 是既有 `--port` 能力,直跑(无 platform/node)路径不变;护栏 + 基线冒烟守住。

## Migration Plan

- 纯代码,优先无 schema 迁移。合并即生效:此后 node 拉起的 agent 带内网端口 + forwarder 起来,平台 `/admin/agents/{name}/chat`·`/ws` 可达托管 agent;materialize 后的托管 agent `.env` 带 `FLEETENT_TUI_TOKEN`。回滚 = `git revert`(门面/forwarder 是新增,移除即回到 IM-only 现状)。
