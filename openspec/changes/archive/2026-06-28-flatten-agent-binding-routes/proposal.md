## Why

`GET /admin/agents/{name}/bindings` 是个**假聚合**：它把 `users`（入向）、`groups`（入向）、`mcp_servers`（出向）三类捆在一个 response 里，却漏掉了另外三类出向绑定（`kbs`/`skills`/`secrets`）。唯一消费者是前端，而前端拿到后**立刻拆开**喂给两个不同 tab（IM tab 用 users+groups，MCP tab 用 mcp_servers）——捆绑零收益。

结果是六类 agent 绑定的路由形态严重不对称：`skills` 已是干净的 per-type（`GET /agents/{name}/skills`、`PUT /agents/{name}/skills/{skill_name}`，无 `/bindings/` 前缀），而 `users`/`groups`/`mcp` 仍挤在 `/bindings/` 命名空间下、读还要走聚合端点。本次把假聚合拆散、六类绑定全部对齐到 skills 的 per-type 形态，消除不对称。

## What Changes

- **BREAKING** 删除聚合读端点 `GET /admin/agents/{name}/bindings`。
- 新增对称的 per-type 读端点：`GET /admin/agents/{name}/users`、`GET /admin/agents/{name}/groups`、`GET /admin/agents/{name}/mcp`（与既有 `GET /agents/{name}/skills`、`/kbs`、`/secrets` 对齐）。
- **BREAKING** 写路由搬出 `/bindings/` 前缀，拍平为 per-type：
  - `POST|DELETE /agents/{name}/bindings/users/{user_id}` → `/agents/{name}/users/{user_id}`
  - `POST /agents/{name}/bindings/groups` + `DELETE /agents/{name}/bindings/groups/{platform}/{group_id}` → `/agents/{name}/groups` + `/agents/{name}/groups/{platform}/{group_id}`
  - `POST|DELETE /agents/{name}/bindings/mcp/{server_id}` → `/agents/{name}/mcp/{server_id}`
- 前端 `features/agents`：用三个 per-type query 替换 `useAgentBindingsQuery`；mutation URL 跟随改动；IM tab 与 MCP tab 各自取数。
- 入向/出向轴**不进 API 契约**（依赖方向本就由 import 护栏强制），仅作为前端 tab 的视觉分组（可选、本次范围外的纯前端整理）。
- 无 schema 改动、无迁移：纯 route/API/前端表层。`agent_secrets`/`agent_kbs` 已是 per-type，不动。

## Capabilities

### New Capabilities

（无新增 capability；本次是既有路由表面的重构。）

### Modified Capabilities

- `agent-admin-api`: 删除 `GET /bindings` 聚合读；新增 `GET .../users|groups|mcp` per-type 读；users/groups/mcp 写路由去 `/bindings/` 前缀。
- `agent-admin-ui`: 取数从单聚合端点改为 per-type 端点；IM tab / MCP tab 各自独立查询。

## Impact

- **代码**：`src/fleetent/platform/agent_management_console/agent_admin_api.py`（删 `get_bindings`、改 6 个写 handler 路由、加 3 个读 handler）。store 层不变（`list_users_for_agent`/`list_mcp_servers_for_agent`/`list_groups_for_agent` 复用）。
- **前端**：`frontend/src/features/agents/api.ts`（替换 bindings hook + 改 mutation URL）、`configure.tsx`（IM/MCP tab 取数）、`api.test.tsx`。
- **测试**：`tests/integration/test_agent_admin_api.py`、`tests/unit/test_coverage_admin_connector_handlers.py`（断言 `get_bindings` 形状，需改写）。
- **不碰**：`agent.yaml` 的 `AgentBindings`（agent 侧 config，同名不同物）；ingress 车道的 `im_gateway_management/` + `features/im`（物理隔离，已核无重叠）；KB connector（另一 change）。
- **迁移**：无。
