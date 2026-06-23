# agent-dual-state-gating — Agent 双态查询 + 启停守卫

## Why

agent 有两套独立的状态，但管理控制台只看得到其中一套：

- **期望态**（desired state）：管理员意图，落在 `agent_admin_state.status`（`enabled` / `disabled` / `archived`）+ `provenance` + `drift`。
- **运行态**（runtime state）：node 实际上报，落在 `node_agent_status`（`phase` / `pid` / `health` / 所在 `node_id`），绑定关系落在 `agent_placements`。

控制台查询端点（`GET /admin/agents` 列表、`GET /admin/agents/{name}` 详情）目前**只返回期望态**，管理员无法在一处看到「我想让它开 / 它现在到底跑没跑、在哪个 node、健康吗」。

此外有两个安全/正确性缺口：

1. **新建即开**：`create` 与 `clone` 落 `status=enabled`（`agent_console_api.create_agent` / `clone_agent` 调 `agent_admin_store.enable`）。但新 agent 尚未 pin 到任何 node，"enabled" 是个空头承诺——`node-desired-state-api` 按 `status=="enabled"` 拉取，没绑定 node 的 enabled agent 根本不会被任何 node 拉起，徒增误导。
2. **enable 无守卫**：`POST /admin/agents/{name}/enable` 不检查 agent 是否已绑定 node，允许把一个无处运行的 agent 置为 enabled。

本 change 让控制台呈现真实双态，并把「enabled」收紧为「已绑定 node 才允许」，使期望态与运行态从源头一致。

## What Changes

1. **查询合并运行态**：`GET /admin/agents` 列表与 `GET /admin/agents/{name}` 详情在原有期望态字段基础上，新增 `runtime`（`phase` / `health` / `pid` / `node_id` / `reported_at`，无上报为 `null`）与 `placement`（`node_id` / `pinned_at` / `pinned_by`，未绑定为 `null`）。既有字段不变、不破坏。
2. **默认关闭**：`create` 与 `clone` 显式落 `status=disabled`，新 agent 默认不进入任何 node 的期望态拉取，直到管理员显式 enable。
3. **enable 守卫**：`POST /admin/agents/{name}/enable` 在 agent 未绑定 node（`placement_store.get_for_agent` 为 `None`）时返回 `409 agent not bound to a node`，不改变状态、不写审计成功记录。`disable` 不加守卫；`restore` 不在本次范围。
4. **前端双态**：Agents 页对每个 agent 同时展示期望态（status）与运行态（running/stopped + health + 所在 node）；当 agent 未绑定 node 时禁用「Enable」控件并给出原因提示。

## Capabilities

### New Capabilities
（无新增 capability；本 change 在既有 capability 上做增量修改。）

### Modified Capabilities
- `agent-admin-api`：列表/详情新增 `runtime` + `placement` 投影；`create` 默认落 `disabled`；`enable` 端点增加「必须已绑定 node」守卫（409）；`clone` 默认落 `disabled`。
- `agent-lifecycle-toggle`：新增「enable 需 agent 已绑定 node」前置约束；明确新建 agent 起始为 `disabled`。
- `agent-admin-ui`：Agents 页展示期望态 + 运行态双态；未绑定 node 时禁用 Enable 并提示。

## Impact

- **owning package**：`platform`
  - `platform/agent_management_console/agent_console_api.py`（列表/详情合并双态、create/clone 默认 disabled、enable 守卫、新增只读 seam）
  - `platform/node_management/node_store.py`（**只读新增** `get_agent_status` / `list_agent_status`，不动既有 `upsert_agent_status` 写入）
  - `platform/node_management/placement_store.py`（**只读新增** `list_placements`；`get_for_agent` 已存在复用）
  - `server.py`（`wire_agent_store_seams` 接线新 seam）
  - 前端 `frontend/src/features/agents/`（`api.ts` 类型扩展、`page.tsx` 双态展示 + Enable gating）
- **public API surface**：
  - `node_store.get_agent_status(agent_id) -> dict | None`、`node_store.list_agent_status() -> list[dict]`（新增只读）
  - `placement_store.list_placements() -> list[dict]`（新增只读）
  - `agent_console_api` 新增模块级注入 seam：`get_agent_runtime` / `get_agent_placement` / `list_agent_runtimes` / `list_agent_placements`
  - HTTP 响应契约：`GET /admin/agents`、`GET /admin/agents/{name}` 新增 `runtime`、`placement` 字段；`POST .../enable` 新增 409 错误码 `agent not bound to a node`
- **owned tables**：无新增。只**读**复用既有 `node_agent_status`、`agent_placements`，**写** `agent_admin_state.status`（经既有 `agent_admin_store.disable`）。无 schema 迁移。
- **config namespace**：无。
- **cross-module dependencies**：`agent_management_console` 经注入 seam 只读 `node_management`（`node_store` / `placement_store`），均在 `platform` 包内（边界检查视 `fleetent.platform.*` 为同一包，合规）。**不碰 agent runtime；无 agent→platform 反向依赖**。运行态仍由 node 经既有 `node-desired-state-api` 写入，platform 侧只读投影。
- **migration / shim**：无表迁移、无模块搬迁；不涉及 re-export shim。
