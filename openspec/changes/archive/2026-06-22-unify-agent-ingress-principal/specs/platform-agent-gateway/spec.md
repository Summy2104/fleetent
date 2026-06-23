## ADDED Requirements

### Requirement: Ingress carries the edge-resolved Principal end to end

托管 ingress SHALL 把**已解析的 `Principal{user_id, tenant_id}`**从解析它的 edge 端到端传到 agent：操作发起方（如 operator）的身份由平台/edge 解析，随转发（平台 → node forwarder → agent）承载，使 agent **按真实用户归属本回合**（会话/记忆/审批 scope by `Principal.user_id`），而非按传输鉴权 token 自身的 principal。

传输鉴权与用户身份 SHALL 分离：传输 token（node service key / `FLEETENT_TUI_TOKEN`）只证明**调用方是可信的 forwarder/TUI**；承载的 Principal 证明**是哪个用户**。承载的 Principal 仅因**传输已通过鉴权**才被信任（受信边界内传递）；未通过传输鉴权的调用 MUST NOT 能注入 Principal。

承载是**向后兼容**的：当入站未携带 Principal（如直连 TUI / 本地 dev），agent SHALL 回退到现行的自解析（按传输 token 解析 principal），standalone（无 platform）下行为不变。

#### Scenario: operator 身份到达 agent

- **WHEN** operator 经 `/admin/agents/{name}/chat`（admin session 已认证）发消息
- **THEN** 平台把 operator 解析成 Principal、随转发承载，agent 用**该 Principal**（operator 的 user_id）归属本回合，而非用传输 token 的 principal

#### Scenario: 跨租户仍被拒

- **WHEN** 承载的 `Principal.tenant_id` 与目标 agent 的租户不一致
- **THEN** agent 按既有 `_check_tenant` 返回 403，承载 Principal 不绕过租户校验

#### Scenario: 未鉴权调用不能注入身份

- **WHEN** 一个未通过传输鉴权（无有效 node key / TUI token）的调用尝试携带 Principal
- **THEN** 请求在传输鉴权处即被拒，承载的 Principal 不被信任、不生效

#### Scenario: 无承载 Principal 时回退自解析

- **WHEN** 入站未携带 Principal（直连 TUI / 本地 dev / standalone）
- **THEN** agent 回退到按传输 token 自解析 principal，行为与现状一致

### Requirement: 统一的 Principal-carrying agent 入站契约

agent 的入站（`/chat` 与 `/ws`）SHALL 接受一个统一形状的输入：可选的 edge 解析 `Principal` + `message`。该契约 SHALL 是后续各类 edge（IM、CLI、open-API 等）共同的目标形状——它们各自解析出 Principal 后产出相同载荷，复用同一条 forwarder→agent 脊柱。本要求**不规定**新增独立端点或端点改名（承载可扩展现有 `/chat`+`/ws`）。

#### Scenario: 多来源产出相同入站载荷

- **WHEN** 不同 edge（如平台 chat-edge）解析出 Principal 并发往 agent
- **THEN** agent 看到统一的 `{principal, message}` 入站形状，处理逻辑不因来源而分叉
