## Why

managed 拓扑下 IM 身份解析是断的：IM adapter + supervisor 现在跑在 **agent 进程**（`agent_app` 启 SlackSupervisor/TelegramSupervisor），但身份绑定（`resolve_or_provision` / im_users）在**平台管理库**，且 agent 进程没注入 resolver、禁写管理库、禁反调 platform → Slack/Telegram 用户在 managed 下解析不成真 user。

方向 B（见 `docs/architecture/identity-channel-ingress.md`）：**IM-edge 下沉 node**（node 是 agent 的本地宿主，且本就合法对接平台）。本切片 = **#4a 入站路径**：node 持 IM 连接 + 经平台解析身份 + 把已解析消息转给本机 agent + 同步回复经 node 发回。异步出站（审批 DM 等）留 **#4b**。

> 契约框定（已与用户确认）：**im_gateway 仍是"不 import platform 的 edge face"**——只是执行宿主从 agent 进程移到 node、注入方从 server.py 变成 node（node 调平台身份解析端点，node→platform 合法）。normalizer + loop 仍在 agent。依赖 #2(resolve_or_provision)、#3(Principal-carrying 入站)，均已落地。

## What Changes

- **IM-edge 移到 node**：SlackSupervisor/TelegramSupervisor 从 `agent_app` boot 移到 **node**——node 为其放置的 agent 持有 Slack(Socket Mode WS)/Telegram(poll) 连接；agent 进程不再启 IM 连接。`connector_registry` 从"agent 进程模块级"调整为 node 侧按 agent 路由。
- **平台身份解析端点**：在 `node_desired_state_api`（`/nodes` 前缀、node service key 鉴权）新增 `POST /nodes/{node_id}/identity/resolve` → 调 `resolve_or_provision(tenant, verified_email?, channel, platform_user_id)` 返回 `Principal`。node 注入一个**调这个端点**的 resolver（im_gateway 仍不 import platform）。
- **node 转发已解析入站**：node IM-edge 收到消息 → 经平台端点解析出 Principal → 把 `{Principal, IM-event}` 转给本机 agent 的 **normalizer 入站**（沿用 #3 的 Principal-carrying 通路）。
- **同步回复经 node 发回**：normalizer 的**同步回复**从"进程内 connector_registry 直发"改为**返回给调用方**，由 node（持连接侧）发回 IM。（这是本切片最实的重构。）
- **agent 侧**：停止在 `agent_app` 启 IM supervisor；新增/复用一个 normalizer 入站（用转发来的 Principal + IM payload 跑 `normalizer.route`→loop），不持连接、不解析身份。

### 不在本切片（#4b / 后续）
- **异步出站**（审批 DM、cron 触发的主动外发——发生在 inbound turn 之外）→ delivery-queue + node drain，留 **#4b**。
- per-tenant IdP / 域映射（身份解析端点吃 tenant 入参，tenant 来源不在此定）。

## Capabilities

### Modified Capabilities
- `platform-agent-gateway`: 新增"node 托管 IM-edge + 平台身份解析端点 + node 把已解析 IM 入站转发给本机 agent normalizer、同步回复经 node 发回"——IM 入站对称于 chat ingress（都经 forwarder 路径、载已解析 Principal）。
- `im-user-mapping`: 身份解析除"平台进程内注入 resolver"外，SHALL 可经 **node→platform 端点**（node service key 鉴权）调用 `resolve_or_provision`；node 注入的 resolver 走该端点。

## Impact

- **owning packages**：`node`（托管 IM-edge supervisor + resolver 注入 + 转发本机 agent + 回复回发）、`platform`（`node_desired_state_api` 加 identity/resolve 端点）、`runtime`（`agent_app` 不再启 IM supervisor；normalizer 入站 + 同步回复返回式）、`im_gateway`（supervisor/adapter 执行位移 node；normalizer 回复路径改返回式；仍 no-platform-import）
- **public API surface**：新增 `POST /nodes/{node_id}/identity/resolve`（node-key 鉴权）；node→agent 的 normalizer 入站（经 forwarder）
- **owned tables**：无（user 经 resolve_or_provision/#2、im_users/#2；无新表）
- **config namespace**：IM 连接配置从 agent.yaml `im` 块投影给 node（node 据 desired-state 知道为哪些 agent 开哪些连接）
- **cross-module dependencies**：node→platform（identity/resolve，node-key 既有通道）；node→本机 agent（转发）；**im_gateway 仍不 import platform**（resolver 注入）；不新增 agent→platform
- **migration / shim**：无 schema；im_gateway supervisor 从 agent 移 node 期间，旧 agent_app 启动路径留兼容（standalone：单进程下 IM 仍可在 agent 进程跑，靠注入方区分）
- **★契约**：更新 AGENTS.md——IM-edge 执行宿主为 node、注入方为 node（im_gateway 仍 no-platform-import edge face）；更新模块依赖护栏对 im_gateway 宿主的描述
- **验证基线**：standalone（无 platform）下 IM 仍能在 agent 进程跑（resolver=None 退化），不破坏 `fleetent agent run`
- 与在飞的 #1(OIDC,平台 login) 不同 surface、零重叠；与 #3(已落地) 复用其 Principal-carrying 入站
