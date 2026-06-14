# descope-model-routes-and-fk-hygiene Tasks

> TDD：每个实现 task 先写测试见红 → 实现见绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。测试任务在实现之前。迁移号 append after head、**勿硬编码**（apply 前 pull 确认）。

## 1. 迁移：drop model_routes + 四表 FK 统一（Alembic）

- [ ] 1.1 [测试] integration：跑到 head 后 `model_routes` 表 + `idx_model_routes_task` 不存在（先红）
- [ ] 1.2 [测试] integration：四表 FK ondelete 正确——`users.tenant_id`/`agents.tenant_id`/`agents.team_id`/`teams.tenant_id` = RESTRICT，`tenants.approver_user_id`/`teams.approver_user_id` = SET NULL（PRAGMA foreign_key_list 断言）；agents 全部列/`UNIQUE(name)`/子表 agents.id CASCADE 保留（先红）
- [ ] 1.3 [测试] integration：行为——删带子实体的 tenant 被 RESTRICT 拒绝；删被 agent 引用的 team 被拒绝；删某 tenant/team 的 approver user → approver_user_id 置空、删用户成功（先红）
- [ ] 1.4 [实现] 新迁移（append after head、勿硬编码）：`DROP TABLE model_routes`（+ 索引）；SQLite batch 重建 `users`/`agents`/`tenants`/`teams` 仅改 FK ondelete（mirror 070/084/085；**agents 重建保列/UNIQUE/子表 CASCADE，照 070 范式**）；downgrade 反向（FK 回 NO ACTION + 重建空 model_routes 表/索引）→ 1.1/1.2/1.3 转绿

## 2. 代码：移除 model_routes 读写 + 路由端点

- [ ] 2.1 [测试] integration：删一个 provider 不再触 model_routes（不报错、无残留路由清理逻辑）；`/admin/providers/routes*` 三端点返回 404（已移除）；`GET /admin/providers/health` 仍在（先红/现态确认）
- [ ] 2.2 [实现] `provider_admin_store`：删 `set_route_order`/`get_route_providers`/`list_route_task_types`；`delete_provider` 去掉手工 `DELETE FROM model_routes WHERE provider_id`
- [ ] 2.3 [实现] `provider_admin_api`：删 `GET /routes`、`PUT /routes/{task_type}`、`GET /routes/{task_type}/preview` 三端点（保留 `/health` 与其余 provider CRUD）→ 2.1 转绿

## 3. audit_log named-params（纯代码、无迁移）

- [ ] 3.1 [测试] unit/integration：`write_audit`/`search_audit` 行为不变（写一条、查回一致）；SQL 用 named params（可断言无 `?` 占位符或经现有用例覆盖）（先红或现态确认）
- [ ] 3.2 [实现] `audit_log.py`：`?` → named parameters（`:name`），签名/行为不变 → 3.1 转绿

## 4. 文档 + spec 同步

- [ ] 4.1 `docs/architecture/data-model.md`：§3.2「模型」段去掉 `model_routes`（model_providers 描述保留）；ER 图删边 `model_providers ||..o{ model_routes : "task→provider·未接线"`；图例「27 条边/8 活」计数随之更新
- [ ] 4.2 `openspec/specs/provider-management/spec.md`：删除陈旧的 `CREATE TABLE model_routes (...)` DDL appendix 块（该表已不存在）
- [ ] 4.3 archive 时同步 delta 到 canonical specs：`task-type-routing-console`（REMOVED 整 capability）、`provider-admin-ui`、`provider-admin-api`、`tenancy-entities`

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：删 provider 路径、FK 删除语义、agent 删除级联仍正常）
- [ ] 5.2 全仓 grep：无残留 `model_routes` 代码引用（迁移历史/归档除外）、无残留 `/routes` 端点引用
- [ ] 5.3 `openspec validate descope-model-routes-and-fk-hygiene` 通过；checkbox 全 `[x]`
