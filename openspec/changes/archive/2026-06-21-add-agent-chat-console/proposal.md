## Why

`prune-platform-dead-debt` 删掉了旧台那个**坏死**的内嵌 chat(它调的 `/admin/chat/*` 平台根本没实现)。现在 ④ `platform-agent-gateway-ingress` 打通了真正的平台→node→agent ingress(`POST /admin/agents/{name}/chat` 流式 + `/ws`),可以把"运维从控制台对话/调试托管 agent"这个能力**以正经方式接回**新 SPA——这次背后是真打通的托管链路,不再是死按钮。

## What Changes

- 新增前端域 `features/chat/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TDD + MSW)。
- 交互:运维先选 agent(复用 `GET /admin/agents`),在对话面板发消息 → 调 **`POST /admin/agents/{name}/chat`**(body `{message}`),**流式读响应**(fetch + `ReadableStream` 增量渲染)。admin Session 认证经 Authorization header(fetch 可设)。
- 错误/不可达(agent 未 placement / 未知 / node 不可达)给清晰提示,不卡死、不空转。
- `app/routes.tsx` 注册 chat 路由 + 导航入口(如 "Chat")。

## Capabilities

### New Capabilities
- `agent-chat-console`: 运维在 SPA 中选择并对话/调试托管 agent——经平台 ingress(`POST /admin/agents/{name}/chat` 流式)+ admin 认证,流式渲染回复,含不可达的明确反馈。

### Modified Capabilities
（无）

## Impact

- **新增**:`frontend/src/features/chat/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 chat + 导航)。
- **后端**:不改(消费 ④ 已实现的 ingress;`agent_transport.chat` 用 `stream=True`+`StreamingResponse` 原样代理 agent SSE 流,已核实)。
- **边界**:纯 `frontend/`;不碰 server.py / agent 运行时 / schema;依赖但不改 ④ 的 ingress。
- **排序/合并**:⑤⑥⑦ 已落地、Connectors 也已原生,本 change 现在是**唯一**动 `routes.tsx` 的前端切片,无并发竞争;**合并由主会话串行做**(窗口只实现 + push 分支,不自行 `git checkout main && merge`)——routes.tsx 对撞事故后的固定规则。
- **不在本切片**:浏览器**双向 WS**(④ 的 `/ws` 经 header 认证、浏览器原生 WebSocket 不能设自定义 header → 需 ④ 补 query-param/subprotocol 认证,属后端跟进);端用户聊天入口。
