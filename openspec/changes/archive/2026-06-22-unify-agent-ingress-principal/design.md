## Context

现状（grounding 已核实）：
- agent `/chat`：`chat(req: ChatRequest, principal: Principal = Depends(_authenticate))`（`agent_app.py:626`），`_authenticate` 走 `_local_bearer(token) or _validate_tui_token(authorization)`（:586），再 `_check_tenant(principal, agent_tenant)`，把 principal 传入 `run_stream`。
- forwarder（`node/forwarder.py:forward_chat`）用 `Bearer <agent 的 FLEETENT_TUI_TOKEN>` 调 agent `/chat`。
- 平台（`server.py` `/admin/agents/{name}/chat`）认证 operator（admin session），经 `DirectHttpAgentTransport`（node service key）→ forwarder。

→ operator 真实身份止于平台；forwarder→agent 这跳 agent 只看到 `_validate_tui_token` 返回的**传输 token principal**。会话/记忆/审批因此归属网关 token，不是真实 user。

## Goals / Non-Goals

**Goals:**
- ingress 端到端承载 **edge 解析的 Principal**；agent 按真实 user 归属本回合。
- 传输鉴权（token = 可信调用方）与用户身份（Principal = 哪个用户）**分离**。
- 向后兼容：无承载 Principal 时回退自解析；standalone 行为不变。
- 确立 `{principal, message}` 入站契约，供后续 edge 复用。

**Non-Goals:**
- 不做 edge-契约注入抽象（resolver/sink）——一个 edge 时过度抽象，留 #4。
- 不挪 IM-edge（#4）、不做 OIDC（#1）/email-join（#2）/`/link`（#5）。
- 不新增/改名端点（不引入 `/message`）——扩展现有 `/chat`+`/ws`。
- 不改 schema、不新增表。

## Decisions

- **D1 · 信任模型：传输鉴权是门，承载 Principal 是门内的字段。** agent 先验传输 token（`_validate_tui_token`/`_local_bearer`，证明调用方是可信 forwarder/TUI）；**通过后**若入站带承载 Principal 则用之、否则回退 token 自解析。未过传输鉴权者根本到不了"读承载 Principal"这步 → 无法注入身份。安全前提沿用现状：agent 仅绑 loopback + token 必需。
- **D2 · 线编码：受信传输头。** Principal 以一个头（如 `X-Fleetent-Principal: <user_id>/<tenant_id>`，或紧凑 JSON）随转发传递，平台→forwarder→agent 逐跳透传。**不单独签名**——因为每跳传输已鉴权（平台→forwarder 用 node key、forwarder→agent 用 TUI token + loopback），信任边界已成立。头缺失即触发回退（D4）。
- **D3 · 解析上移到平台 chat-edge。** `/admin/agents/{name}/chat` 把已认证 operator（admin session → user）解析成 `Principal`，交给 `DirectHttpAgentTransport.chat(...)` 随转发承载。`agent_transport` 与 `forwarder` 仅**透传**该头，不解析。
- **D4 · agent 消费 + 回退。** `_authenticate`/入站处：传输 token 验过后，若有承载 Principal → 用承载的（覆盖 token 自身 principal）；无 → 维持现行 `_local_bearer/_validate_tui_token` 自解析。`_check_tenant(principal, agent_tenant)` **保持不变**、对承载 Principal 同样生效。
- **D5 · `/ws` 同构处理**：WebSocket 入站同样在传输鉴权后读承载 Principal（连接建立握手阶段），无则回退。

## Risks / Trade-offs

- **承载头被信任的前提是传输边界成立**：必须确保 agent 只在 `_validate_tui_token`/node-key 验过之后才读该头；任何"先读头后验 token"的写法都是漏洞。测试需覆盖"无有效 token + 带伪造 Principal 头 → 被拒、头不生效"。
- **operator 的 Principal 租户**：admin operator 测一个**非自身租户**的 agent 时，承载 `Principal.tenant_id` 与 agent 租户不一致会被 `_check_tenant` 拒（403）。本切片**不扩大** `_check_tenant`——保持现约束（D3 实测 default 租户 demobot 可用）；跨租户管理员控制台是单独议题，记 deferred，不在本切片解。
- **回退路径必须真覆盖**：直连 TUI / 本地 dev / standalone 都走"无承载 Principal → 自解析"。回归测试要确认这些路径行为零变化（否则破坏 `fleetent agent run` 验证基线）。
- **ws 承载时机**：WebSocket 没有逐消息 header，承载 Principal 要在**连接握手**阶段带入并钉住整条连接；测试需覆盖握手期注入 + 整连接归属一致。
