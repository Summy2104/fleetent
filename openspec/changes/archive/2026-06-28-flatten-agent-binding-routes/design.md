## Context

减法系列（retire-tool-oauth-vault、slim-mcp-to-agent-auth）净化绑定族后，platform 侧六类 agent 绑定的 HTTP 形态仍不对称：

```
出向  agent_kbs      GET/POST/DELETE /agents/{n}/kbs[/{kb_id}]        ← per-type ✅
出向  agent_skills   GET /agents/{n}/skills · PUT .../skills/{name}   ← per-type ✅
出向  agent_secrets  GET /agents/{n}/secrets · PUT/DELETE .../{env}   ← per-type ✅
出向  agent_mcp      POST/DELETE /agents/{n}/bindings/mcp/{id}        ← /bindings 前缀 ✗
入向  user_agents    POST/DELETE /agents/{n}/bindings/users/{id}      ← /bindings 前缀 ✗
入向  agent_im_groups POST /agents/{n}/bindings/groups · DELETE ...   ← /bindings 前缀 ✗
读    （上面三类）    GET /agents/{n}/bindings  ← 假聚合,漏 kbs/skills/secrets ✗
```

`GET /bindings` 唯一消费者是 admin 控制台（`useAgentBindingsQuery`），取数后立刻拆给 IM tab（users+groups）与 MCP tab（mcp_servers）。无 CLI、无跨服务、无 materialize 依赖该聚合形状。

## Goals / Non-Goals

**Goals:**
- 六类绑定 HTTP 形态完全对称，全部 per-type，向既有 skills/kbs/secrets 形态看齐。
- 删除假聚合 `GET /bindings`，代之以 `GET .../users|groups|mcp` 三个 per-type 读端点。
- users/groups/mcp 写路由搬出 `/bindings/` 命名空间。
- 前端 agents feature 改为 per-type 取数，行为不变（仍是同样的 tab、同样的 add/remove）。

**Non-Goals:**
- 不引入入向/出向的 API 契约层（依赖方向由 import 护栏强制，不需 response 反映）。入向/出向只作可选的前端 tab 视觉分组，本次不做。
- 不改 store 层（复用 `list_users_for_agent`/`list_mcp_servers_for_agent`/`list_groups_for_agent`/`assign_user`/`bind_mcp_server` 等）。
- 不改 schema、不加迁移。
- 不碰 KB connector 改名（另一并行 change）。
- 不碰 agent.yaml 的 `AgentBindings`（agent 侧 config，同名不同物）。

## Decisions

- **per-type 读端点命名 `/agents/{n}/mcp`**（非 `/mcp-servers`）：与既有写路由 `/bindings/mcp/` 的 `mcp` 段一致，最短且无歧义。users/groups 同理用复数名词，与 `/skills`/`/kbs`/`/secrets` 一致。
- **读权限沿用**：per-type 读端点 viewer+admin 可读、未知 agent 返回 404，与原聚合端点一致。
- **写路由迁移是 BREAKING、无兼容期**：唯一消费者是同仓前端，一次性改完即可，不保留 `/bindings/` 旧路由 alias（留 alias 等于没拆干净）。
- **agent-admin-ui spec 顺手清掉死 OAuth 引用**：原 "Agent bindings and native configuration" 要求里 Connectors 项仍引用 `GET /admin/connectors` 与 `/bindings/oauth`——这些端点已被 retire-tool-oauth-vault 删除，是未同步的 spec drift。本次重写该要求时一并去除（不能在 desired-state spec 里再 bless 已删路由）。

## Risks / Trade-offs

- **BREAKING 路由变更**：前端 mutation URL + integration test 路由串需同步改。缓解：唯一消费者同仓，`api.test.tsx` 与 `test_agent_admin_api.py` 是改动闸门，红→绿即覆盖。
- **agent-admin-api spec 残留的 "Agent OAuth connector binding endpoints" 要求**（line 308 一带）同属 retire 未同步的 drift，但本 change 不重写该要求、不在范围内——仅记录，留给后续 spec 同步处理，避免本 change 范围蔓延。
- **入向/出向分区延后**：本次只拆平、不分组，若日后控制台想要 Access/Capability 两段式 tab，是纯前端增量，无需再动 API。
