## Why

平台侧累积了一批「死代码 / 死路由 / 死列 / 坏死 UI」：调用不存在后端的 UI 按钮、已被替代但留作 404/409 墓碑的端点、规格早已声明删除却仍物理存在的列、以及无任何调用方的孤儿 API。它们不构成功能，却让 UI 出现点了报错的按钮、让规格与代码互相矛盾、增加阅读与维护负担。本次做一轮**纯债务清理**：只删确证无用之物，不动产品能力、不动「后端齐·UI 缺」的半成品、不缩减多租户/多节点/KB/技能治理等结构。

## What Changes

按「垂直切片」拔除，每个切片内部按 UI → API → 表的顺序删除，保证每步系统仍可运行、可测：

- **删 observability 孤儿 API**：移除 `observability_management/` 整模块（`__init__.py` + `observability_admin_api.py`）及 `server.py` 的 router 注册。该 API 的 `/admin/observability/{traces,usage,performance}` 无任何 UI / CLI / 测试调用方；UI 的分析功能全部走 `stats-admin-api`。**BREAKING**（移除未被使用的 HTTP 端点）。
- **删 Provider 路由墓碑**：移除 `provider_admin_api.py` 中 `/routes`、`/routes/{task_type}`、`/routes/{task_type}/preview` 三个已返回 404 的桩端点及 `_routes_removed` 辅助函数；删 admin UI 中的 Providers→Routes 区块。模型路由真相早已迁至 `ROUTES_PATH` YAML 与 agent `model_overrides`，管理 DB 表 `model_routes` 已在迁移 086 删除。
- **删 Chat playground 死 UI**：移除 admin UI 的 Chat 标签页与 Sessions 页的 playground 子面板（调用平台不存在的 `/admin/chat/{start,sessions,...}`）。**保留** Sessions 治理能力（接管 / 释放 / 注入 / 强制结束 / 清空 / 重置）不变。
- **删 Stats reports 死调用**：将 `stats-admin-ui` 的「导出与报表」收缩为仅导出（`POST /admin/stats/export` 真实存在）；移除调用不存在的 `POST /admin/stats/reports` 的报表按钮。
- **删 skill 提案的平台审批桩**：移除 `skill_admin_api.py` 中 `POST /admin/skills/proposals/{id}/approve`、`/reject` 两个已返回 409 的桩端点及 UI 上对应按钮。**保留**提案列表与 diff 查看（`GET /proposals`、`GET /proposals/{id}/diff` 真实读取 reflection）。技能提案审批已是 **agent-owned、经 DM 投递**的模型（平台只读下游投影）；本次同时把仍要求平台审批的 stale 规格（`skill-proposal-review`、`skill-admin-ui`）与该现实对齐。
- **删 `im_users.allowed` 死列**：forward 迁移 drop 该列；清理 `im_gateway_management/identity.py` 中对它的兼容 shim 引用。IM 身份解析早已一律走 `users.status`，`im-user-allowlist` 规格亦已声明该 flag removed——本次让 schema 与规格一致。

不动：多租户 / 多节点编排 / KB 内容生命周期 / 技能治理结构；以及一切「后端 + 表已齐、仅缺 UI」的半成品（agent IM 访问、默认 agent、API key 吊销、节点编排 UI 等），单列为「待接 UI」backlog，不进本次减法。

## Capabilities

### New Capabilities
（无——本次为纯删除/收缩变更）

### Modified Capabilities
- `observability-admin-api`: 能力整体退役，删除其全部 requirement（无调用方的孤儿 HTTP 端点）。
- `session-admin-ui`: 删除「Chat playground」requirement；其余 Session 控制动作 requirement 保持不变。
- `session-admin-console`: 「Chat management permissions and audit」requirement 中移除对 playground 试聊的引用（含 viewer「不可发起 playground 试聊」场景）；「Session list and search」对 `origin=playground` 的排除子句保留（仍是正确且无害的过滤），其余治理 requirement 不变。
- `stats-admin-ui`: 「Export and reports」requirement 收缩为仅 export，删除「generate a report」语义。
- `skill-proposal-review`: 删除「Approve proposal」「Reject proposal」两条要求平台侧写入的 requirement（审批已 agent-owned，经 DM）；保留提案 inbox 列表与 diff requirement。
- `skill-admin-ui`: 「Skill proposal review」requirement 收缩为「列出提案 + 查看 diff」，删除 approve/reject 动作。

### 无需 spec delta（code/schema-only 对齐）
- Provider 路由墓碑：`provider-admin-api` 规格已声明路由真相离开管理 DB，删 404 桩不改 requirement。
- `im_users.allowed` 删列：`im-user-allowlist` 规格已声明该 flag removed，删列只是让 schema 追上规格。

## Impact

- **删除代码**：`src/fleetent/platform/observability_management/`（整模块）；`server.py` 第 230 行 router 注册；`provider_admin_api.py` 的 3 个 404 路由桩 + `_routes_removed`；`skill_admin_api.py` 的 2 个 409 提案审批桩；`static/admin.html` 中 Chat 标签页、Sessions playground 子面板、Providers→Routes 区块、Stats 报表按钮、skill 提案 approve/reject 按钮；`im_gateway_management/identity.py` 中 `im_users.allowed` 兼容 shim。
- **数据库**：新增一支 forward 迁移 drop `im_users.allowed`（其余 `agent_state` / kb / shared_memory 嵌入式迁移不涉及）。
- **公共 API 表面**：移除 `observability_admin_api.router`、provider routes 三端点、skill proposals approve/reject 两端点；其余 surface 不变。
- **模块边界**：改动全部落在 `platform` 包与 `static/admin.html`；agent 运行时（`runtime`/`session`/`im_gateway` 运行路径/`memory` 等）不受影响。验证基线「无 platform、platform DB 表不存在时 agent 仍能 `agent run` 对话」不受本次改动影响。
- **测试**：删除 / 调整断言上述端点存在或 UI 调用它们的单元/集成测试；`im_users.allowed` 删列后补迁移测试与 IM 身份解析回归（确认仍走 `users.status`、insert 路径不再写 `allowed`）。
