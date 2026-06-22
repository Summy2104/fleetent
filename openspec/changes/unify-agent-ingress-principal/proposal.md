## Why

托管 ingress 当前**把 operator 的真实身份丢在 forwarder→agent 这一跳**：

- 平台 `/admin/agents/{name}/chat` 认证 operator（admin session），但转发时 DirectHttp transport 经 forwarder 用 **`Bearer <FLEETENT_NODE/TUI token>`** 调 agent `/chat`。
- agent 的 `_authenticate` 走 `_validate_tui_token` → 返回的是**那个传输 token 对应的 principal，不是发起对话的真实 operator**（`agent_app.py:586`）。

即：**agent 认证的是「传输」（token 证明调用方是可信 forwarder/TUI），不是「用户」**。结果托管 chat 的会话/记忆/审批都归属到一个 per-agent 的网关 token 身份，而非真实 user。这是 `身份属 edge、核心只消费 Principal` 原则没落到 ingress 的具体缺口——也是后续 IM-edge(#4)、CLI、open-API 等所有 edge 共同依赖的地基：**edge 解析出 Principal、穿过 forwarder 传给 agent、agent 在传输信任边界内消费它**。

> 这是 `docs/architecture/identity-channel-ingress.md` 切片 #3（统一入站 + edge 契约的地基部分）。

## What Changes

- **ingress 载 edge 解析的 Principal**：在平台→forwarder→agent 的转发上，新增承载一个**已解析的 `Principal{user_id, tenant_id}`**（编码为受信传输头/字段，仅因传输已鉴权才被信任）。
- **平台 chat-edge 解析 operator → Principal 并传入**：`/admin/agents/{name}/chat` 把已认证 operator 解析成 Principal，随转发下发。
- **agent 在传输信任边界内消费传入 Principal**：当 /chat（及 /ws）经受信传输（node-key/TUI token 已验）携带 Principal 时，agent **用传入 Principal**（而非用 token 自身的 principal）；保留**直连 TUI 无携带 Principal 时回退自解析**（本地 dev / 直连 TUI）。
- 确立 `{principal, message}` 作为 agent 入站契约——后续 edge（IM/CLI/API）产出相同形状，复用同一脊柱。
- **不破坏**既有流式契约（fix-streaming 的 client 生命周期）、node-key/TUI 传输鉴权、tenant 校验（`_check_tenant`）。

### 明确不在本切片（deferred）
- 完整的 edge-契约**注入抽象**（resolver/sink）——只一个 edge（chat）时是过度抽象，等 #4 第二个 edge（IM-edge）再成型。
- IM-edge 下沉 node（#4）、OIDC（#1）、email-join/im_users 演进（#2）、`/link`（#5）。
- 入站端点**改名**为 `/message` —— 纯命名/cosmetic，本切片**扩展现有 `/chat`+`/ws`** 承载 Principal，不新增端点、不改路由名（避免大爆炸）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `platform-agent-gateway`: ingress SHALL 端到端承载**已解析的 Principal**——operator/edge 解析的身份必须到达 agent，agent 按它归属会话（而非按传输 token 的 principal）；传输鉴权与用户身份分离（token 证明「可信调用方」，Principal 证明「哪个用户」）。

## Impact

- **owning packages**：`platform`（`server.py` chat 端点解析+下发 Principal；`node_management/agent_transport.py` 转发携带 Principal）、`node`（`node/forwarder.py` 中继 Principal）、`runtime`（`agent_app.py` 入站消费传入 Principal + 回退）
- **public API surface**：`/admin/agents/{name}/chat`、forwarder `/forward/agents/{name}/chat`、agent `/chat`+`/ws` 的入站载荷新增可选 `principal`（受信传输头/字段）；签名向后兼容（无 Principal 时回退现行为）
- **owned tables**：无
- **config namespace**：无（沿用 `FLEETENT_TUI_TOKEN` 作传输鉴权）
- **cross-module dependencies**：不变方向；平台解析 operator→Principal 用既有 user_store；**不新增 agent→platform**
- **migration / shim**：无 schema/迁移；入站载荷向后兼容（旧调用无 principal → 回退）
- 不碰 frontend、不碰 KB/记忆（与车道 A/B/C 零重叠）；不破坏 agent↔platform 解耦与验证基线（standalone 无 platform 时 agent 仍能自解析跑）
