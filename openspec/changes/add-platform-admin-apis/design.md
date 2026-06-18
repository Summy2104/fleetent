## Context

平台 HTTP 服务（`server.py`）已注册 11 个 router，涵盖用户、agent、KB、技能、节点期望态等管理接口。但以下四块管理操作只有 `fleetent-admin` CLI 入口，HTTP API 缺位或未接线：

1. **租户/团队管理**：`platform/tenancy/admin_api.py` 已实现完整的 6 条路由（`CreateTenant`/`ListTenants`/`CreateTeam`/`ListTeams`/`SetUserTenant`/`SetApprover`），但**未在 `server.py` 中 `include_router`**——router 存在却死代码。
2. **节点管理**：`node_desired_state_api.py` 是 node→platform 拉取/上报 API（`/nodes/{id}/desired-state`），无 admin 侧注册/注销/pin 的 HTTP 入口；`platform/node_management/` 下无 `node_admin_api.py`。
3. **共享记忆管理**：`platform/admin_cli/shared_memory.py` CLI 直接调用 `fleetent.memory` 公共 API，平台侧无 HTTP router；`platform/` 下无独立 shared memory 管理模块。
4. **KB 实体提取触发**：`kb_admin_api.py` 已注册且有连接器管理端点，但无 `extract-entities` 触发端点；CLI 在 `admin_cli/kb_connectors.py` 中实现。

## Goals / Non-Goals

**Goals:**
- 激活已有但未接线的租户管理 API（一行 `server.py` 改动）
- 新建节点管理 admin HTTP router（`/admin/nodes/*`）
- 新建共享记忆 admin HTTP router（`/admin/memory/shared/*`）
- 在现有 `kb_admin_api` 中新增实体提取触发端点

**Non-Goals:**
- 修改 `fleetent-admin` CLI（由后续 `slim-admin-cli` change 处理）
- 修改 node-to-platform 的 desired-state/status API（不变）
- 添加 UI（后续 change 按需处理）
- 为新端点添加分页（v1 全量返回，数据量可控）

## Decisions

### D1：租户 API 只需接线，无需新代码

`tenancy/admin_api.py` 的 6 条路由已实现完整业务逻辑（含 `_require_admin` 鉴权和 `audit_log.write_audit` 审计）。只需在 `server.py` 加一行 `include_router`。不重写、不移动代码。

URL 前缀保持现有实现的 `/admin/tenancy`（而非 proposal 中写的 `/admin/tenants`）——改前缀会破坏任何已有调用，不值得重构。

### D2：节点管理 admin API 新文件，鉴权复用 session token

在 `platform/node_management/node_admin_api.py` 新建 router（`prefix="/admin/nodes"`），鉴权方式与其他 admin router 一致（`Authorization: Session <token>` + `_require_admin`），不复用 node service key 鉴权（后者是 node 自身用的，不是管理员用的）。

端点：
- `POST /admin/nodes` — 注册 node（返回一次性明文 service key）
- `GET /admin/nodes` — 列举所有 node
- `DELETE /admin/nodes/{node_id}` — 注销（有 pin 保护约束，复用 `node_store` 现有逻辑）
- `POST /admin/nodes/{node_id}/pin` — pin 指定 agent 到 node
- `DELETE /admin/nodes/{node_id}/pin` — unpin

实现层面直接复用 `node_store` 和 `placement_store`，与 CLI 调用的是同一底层函数。

### D3：共享记忆 HTTP API，platform 可调 `fleetent.memory`

架构允许 platform → agent runtime 单向依赖。`fleetent.memory` 是 agent 运行时模块，platform 调用它不违反边界（CLI 已经这样做）。

在 `platform/shared_memory_management/shared_memory_admin_api.py` 新建 router（`prefix="/admin/memory/shared"`），直接调用 `fleetent.memory.list_shared_memory`、`create_shared_memory`、`update_shared_memory`、`archive_shared_memory` 公共 API。

scope 由 query 参数传入（`scope_type` + `scope_id`），与 CLI 参数一致。审计通过现有 `audit_log.write_audit`。

### D4：KB 实体提取在现有 `kb_admin_api.py` 追加端点

不新建文件。在 `platform/knowledge_base_management/kb_admin_api.py` 末尾追加 `POST /admin/kb/{kb_id}/extract-entities`，调用现有 KB 实体提取入口（与 CLI `_handle_extract_entities` 调用相同函数）。

### D5：所有新 router 统一在 `server.py` 接线

按现有模式（`app.include_router(xxx.router)`）在 `server.py` 末尾追加新 router 注册，不改变现有注册顺序。

## Risks / Trade-offs

- **共享记忆 scope 路由**：HTTP API 要求调用方明确传 `scope_type`/`scope_id`，无法像 CLI 一样依赖运维人员的上下文判断。接口设计上要求这两个参数必填，不做默认推断。→ 接口更显式，文档说清楚。
- **节点注册返回一次性 key**：`POST /admin/nodes` 返回明文 service key，之后不可再查。HTTP 响应需要明确标注这一行为，避免调用方误以为可以重新获取。→ 响应体加 `service_key_plaintext_once` 字段名暗示一次性语义。
- **租户 API URL 前缀 `/admin/tenancy`**：与 REST 惯例（`/admin/tenants`）不一致，但现有实现如此。不在本 change 修复，留技术债注记。

## Migration Plan

1. 按 tasks 顺序实现，每步 TDD
2. 每个新 router 均有 integration 测试覆盖 happy path + auth 拒绝场景
3. `server.py` 接线后，现有 integration 测试套件验证无回归
4. 部署：无 DB 迁移，无停机要求，滚动部署即可
