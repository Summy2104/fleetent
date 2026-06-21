## Why

托管(node)模式下,agent 这一层目前**零入站端口**:node 拉起 agent 时不带 `--port`,agent 不暴露 `/chat`·`/ws`;IM 走出站(Socket Mode / 长轮询)。结果运维**无法从控制台对话或调试任何托管 agent**——这正是试用时撞到的痛点。本切片打通"平台→node→agent"的入站可达闭环,采用三层划分:**Platform 当唯一对外门面、Node 当协调管道、Agent 在内网端口上提供 gateway**;reach 先用最简的 (i) 平台直连,藏在一个 transport 抽象后,日后可无痛换成 (ii) node 反向出站通道。

## What Changes

- **Agent gateway**:坐实 agent 在 node 分配的内网端口上提供 `/chat`·`/ws`(已有,经 `--port`),认证沿用 `FLEETENT_TUI_TOKEN`。
- **B3 · node 带端口起 agent**:`node/backend.py` 的 Popen 改为带**仅内网** `--port` 起 agent,并登记该端口(优先放 `node_agent_status` 或进程内,无 schema 则不加迁移)。
- **Node forwarder(新建)**:node 起一个**仅内网**的转发器,受 **node key** 认证;把平台转来的请求送到本机目标 agent 的 localhost 端口,并注入该 agent 的 `FLEETENT_TUI_TOKEN`(node 从它写的 `.env` 持有)。
- **B2 · materialize 供给 token**:materialize 为**托管 agent** 供给 `FLEETENT_TUI_TOKEN`(托管 agent 不走 `agent init`)——改 `materialize._seed_env`(与已合并的 A 改的 `_strip_secret_plumbing` 是同文件不同函数)。
- **平台门面 + 路由 + transport seam**:平台暴露 ingress(`/admin/agents/{name}/chat` 与 `/ws`),以 **admin** 认证运维,按 **placement**(`placement_store` 查 agent→node)路由到目标 node,调 `AgentTransport` 接口的 **DirectHttp** 实现 →(node key)→ node forwarder。契约**支持流式**(WS/SSE),为 (ii) 反向通道留口。
- **认证链**:运维 →(admin Session)→ 平台 →(node key)→ node forwarder →(agent `FLEETENT_TUI_TOKEN`,node 注入)→ agent。平台不持 agent token。

## Capabilities

### New Capabilities
- `platform-agent-gateway`: 平台→node→agent 的入站可达能力——平台门面 ingress、按 placement 路由、`AgentTransport` 抽象(DirectHttp 实现,流式契约)、node 内网 forwarder、以及端到端认证链。

### Modified Capabilities
- `tui-agent-token-auth`: 新增"materialize 为托管 agent 供给 `FLEETENT_TUI_TOKEN`"——补上托管 agent(不走 `agent init`)的 token 供给路径。

## Impact

- **改动代码**:`src/fleetent/runtime/agent_app.py`(少量,坐实 gateway/auth)、`src/fleetent/node/`(backend Popen 带端口 + 新 forwarder + transport 接收侧)、`src/fleetent/server.py`/platform(门面 + 路由 + `AgentTransport` DirectHttp)、`src/fleetent/platform/agent_lifecycle/materialize.py`(B2)。
- **公共 API 表面**:平台新增 `/admin/agents/{name}/chat`·`/ws` ingress;node 新增内网 forwarder 端点(node key 认证)。
- **边界**:`platform→agent` 是**允许**方向(被禁的是 agent→platform 反向 import)——不破坏解耦;不要求 agent/node 反向 import platform;**不破坏 desired-state 不含明文密钥契约**(token 经既有 secret 路径下发,不进 desired-state config 明文)。验证基线(无 platform 时 `agent run` 直跑)不受影响——agent gateway 是既有 `--port` 能力。
- **并行**:碰 server.py/node/agent_app/materialize,与正在跑的 3 个前端域 change(纯 `frontend/`)**零文件重叠**,安全并行。B2 改 materialize 的 `_seed_env`,与已合并的 A(`_strip_secret_plumbing`)同文件不同函数。
- **schema**:优先无迁移(端口登记放 `node_agent_status` 现有列或进程内);若确需持久化新列,再评估加迁移。
- **不在本切片**:运维聊天/调试**前端页**(后续前端域 change)、通用第三方 **webhook 路由**(后续切片)、(ii) **反向通道**实现(仅留接口口子)。
