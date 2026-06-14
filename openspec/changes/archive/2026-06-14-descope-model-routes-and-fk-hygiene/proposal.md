# descope-model-routes-and-fk-hygiene

> 平台侧清理三合一。**合一个 change 的原因**：三块都加 Alembic 迁移（单链，分开必分叉双头）且都改 `data-model.md`，无法并行。已核当前无未归档 change 碰这些文件；head=085（新迁移 086，**勿硬编码**）。

## Why

平台侧实测审计（2026-06-14，对照 alembic head + 消费方）暴露：
1. **`model_routes` 表是 build-but-unwired**：admin 路由控制台（`task-type-routing-console`）写读它，但 **runtime 模型选型从不读这张表**——真实路由走两套**别的**机制：per-agent 的 `agent.yaml` `model_overrides`（`agent-scoped-model-routing`）与全局 `ROUTES_PATH` YAML 文件（`model-routes-externalize`）。这张表 + 其控制台是从未接线的并行机制。
2. **`audit_log` SQL 用 `?` 占位符**，偏离 AGENTS.md「store 统一 named parameters」规约。
3. **租户/团队/审批人 FK 缺删除语义且 fresh/legacy 分叉**：`users.tenant_id` 在全新库=RESTRICT、从旧库升上来=NO ACTION；`agents.tenant_id`/`team_id`、`tenants`/`teams.approver_user_id` 全是裸 NO ACTION。删 tenant/team/approver-user 的行为既不一致也无保护。

## What Changes

### 1. descope model_routes（移除 task-type 路由控制台）
- **Alembic 迁移**：`DROP TABLE model_routes`（+ 索引 `idx_model_routes_task`）。
- **store**：删 `provider_admin_store` 的 `set_route_order` / `get_route_providers` / `list_route_task_types`；删 `delete_provider` 里手工的 `DELETE FROM model_routes WHERE provider_id`（表没了，无需兜底）。
- **API**：删 `provider_admin_api` 的 `GET /routes`、`PUT /routes/{task_type}`、`GET /routes/{task_type}/preview` 三个端点（`GET /health` 是 `provider-health-probe`，**保留不动**）。
- **capability**：`task-type-routing-console` 整个 **REMOVED**（控制台核心功能=编辑一张 runtime 不读的表）；`provider-admin-ui` 删「Task-type routing」requirement；`provider-admin-api` 去掉 listing 的「routing context」与 delete 的「from all task_type routes」措辞；`provider-management` 去掉 `model_routes` 建表 DDL 并把「Intelligent Task-Type Routing」改指向 agent.yaml / ROUTES_PATH 实机制。
- **不动**：`model-routes-externalize`（YAML 文件机制，runtime 真在用）、`agent-scoped-model-routing`、`provider-health-probe`（`/health`）。provider-health-probe 数据仍在，将来想要路由健康视图可单独加回。
- **文档**：`data-model.md` §3.2「模型」段去掉 `model_routes`；ER 图删边 `model_providers ||..o{ model_routes`。

### 2. audit_log named-params（纯整洁、无迁移）
- `audit_log.py` 的 `write_audit` / `search_audit` 把 `?` 占位符改为 named parameters（`:name`）；函数签名与行为不变。

### 3. FK ondelete 统一（policy：父删 RESTRICT + approver SET NULL）
- **Alembic 迁移**（SQLite batch 重建，mirror 070/084/085）：
  - `users.tenant_id` → tenants：统一 **ON DELETE RESTRICT**（修掉 fresh/legacy 分叉）。
  - `agents.tenant_id` → tenants、`agents.team_id` → teams：**RESTRICT**。
  - `teams.tenant_id` → tenants：已是 RESTRICT，保持。
  - `tenants.approver_user_id` → users、`teams.approver_user_id` → users：**ON DELETE SET NULL**（列本就 nullable）。
- 删一个仍挂着 users/agents/teams 的 tenant、或仍被 agents 引用的 team → 被 RESTRICT 拒绝（不误删数据）；删一个当审批人的 user → 对应 `approver_user_id` 置空。
- **agents 重建谨慎**：agents 被 ~11 张子表 FK 引用；保留 agents 全部列 / `UNIQUE(name)` / 既有 tenant_id&team_id FK（仅改 ondelete），不破坏子表 CASCADE。070 已用 batch 重建过 agents，有先例。downgrade 反向回 NO ACTION。

## Capabilities

### Removed Capabilities
- `task-type-routing-console`: admin 路由控制台整体移除——其编辑/预览的 `model_routes` 表 runtime 从不消费（模型路由真相源是 agent.yaml + ROUTES_PATH）。

### Modified Capabilities
- `provider-admin-ui`: 删「Task-type routing」（不再有 `/routes` 端点 / 路由编辑 UI）。
- `provider-admin-api`: provider listing 去掉「owning task_type / fallback priority」routing context；delete provider 去掉「removed from all task_type routes」（model_routes 已不存在）。
- `provider-management`: 移除 `model_routes` 建表 DDL；「Intelligent Task-Type Routing」requirement 改述为「路由真相源 = agent.yaml model_overrides + ROUTES_PATH YAML」，不再依赖管理库 model_routes 表。
- `tenancy-entities`: tenant/team/agent 的归属 FK 声明父删 **RESTRICT**、`approver_user_id` FK 声明 **SET NULL**（统一删除语义、修 fresh/legacy 分叉）。

## Impact

- **owning package**：`platform`（Alembic 迁移 + `model_provider_management/provider_admin_store.py` & `provider_admin_api.py` + `audit_log.py` + 租户 FK 迁移）。
- **public API surface**：移除 `/admin/providers/routes`、`/admin/providers/routes/{task_type}`(PUT)、`/admin/providers/routes/{task_type}/preview` 三端点（admin 面；仓库内无消费方，外部 admin UI 若有路由编辑页会失效——按「整个控制台撤」已确认）。`audit_log` / store 其余函数签名不变。
- **owned tables**：`DROP model_routes`；`users`/`agents`/`tenants`/`teams` 的 FK ondelete 变更（无列/值变更）。
- **config namespace**：无（`ROUTES_PATH` YAML 机制不动）。
- **cross-module dependencies**：不碰 agent 零 platform import；`audit_log` 是顶层 infra。
- **migration / shim plan**：append after head（086，勿硬编码）；SQLite batch 重建保留主键/唯一/索引；forward-only + 反向 downgrade（FK 回 NO ACTION、不重建 model_routes——drop 类不可逆数据，但 pre-launch 窗口可重置）。
- **相邻切片**：已核 `delivery-receipts-postcondition` / `knowledge-base-standalone-service` / `unified-file-exchange` 均不碰本 change 文件；apply 前 pull 确认 head 与无新增碰撞。
