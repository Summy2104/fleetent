# 设计：descope-model-routes-and-fk-hygiene

## D1 — descope model_routes（不接线、整个控制台撤）

**结论**：删 `model_routes` 表 + `task-type-routing-console` capability，而非把它接线。

依据：runtime 模型路由有两套**真实在用**的真相源——① per-agent `agent.yaml` `model_overrides`（`agent-scoped-model-routing`，materialize 投影）② 全局 `ROUTES_PATH` YAML（`model-routes-externalize`，model_router 启动加载）。`model_routes` 管理库表只被 `provider_admin` 的 `/routes` 控制台端点写读，**runtime resolver 从不查它**（agent 实测 + store 自述「接线是 follow-up」）。即它是从未连上 runtime 的并行编辑面——编辑的是一张没人读的表，预览的是 fiction。故整体移除。

**不动**：`model-routes-externalize`（YAML 机制）、`agent-scoped-model-routing`、`provider-health-probe`（`GET /admin/providers/health` 保留）。撤控制台不影响"哪个 provider 挂了"的数据源；将来如需独立路由健康视图可单独加。

**spec 面**：task-type 路由散在 4 个 capability——`task-type-routing-console`（REMOVED 全部）、`provider-admin-ui`（REMOVED「Task-type routing」）、`provider-admin-api`（MODIFIED：listing 去 routing context、delete 去「from all task_type routes」）、`provider-management`（陈旧 `model_routes` 建表 DDL 是 appendix 非 requirement → apply 时直接从 canonical spec 删该 DDL 块；其「Intelligent Task-Type Routing」requirement 描述的 runtime 行为仍真，不动）。

## D2 — FK 删除语义：父删 RESTRICT + approver SET NULL

- **父删 RESTRICT**（tenants→users/agents/teams、teams→agents）：删一个还挂着子实体的主体/团队直接拒绝，强制显式迁移/清理，绝不静默级联删 users/agents（太破坏）。同时修掉 `users.tenant_id` 在 fresh（RESTRICT）/legacy（NO ACTION）的分叉。
- **approver SET NULL**（tenants/teams.approver_user_id→users）：审批人离职不该阻塞删用户、也不该波及主体；置空后由审批解析链 fallback / default-closed 处理（列本就 nullable）。
- 为什么不 CASCADE：删 tenant 连带清空其全部 users/agents/teams 太激进，v1 无此 offboard 需求；要时再单列。

## D3 — agents 批量重建风险（最需谨慎处）

`agents` 被 ~11 张子表 FK 引用（user_agents/channel_agents/agent_versions/agent_admin_state/agent_kbs/agent_skills/mcp_servers/agent_mcp_servers/agent_oauth_bindings/agent_secrets/session_meta）。改 `agents.tenant_id`/`team_id` 的 ondelete 需 SQLite batch 重建 agents：
- **必须保留** agents 全部列、`UNIQUE(name)`、`active_version_id`（裸列无 FK）、既有 tenant_id&team_id FK（仅改 ondelete=RESTRICT）。
- **不得破坏子表的 agents.id CASCADE**：子表 FK 指向 `agents(id)`，batch 重建 agents 时按 alembic batch_alter_table 范式（建新表→拷数据→drop 旧→rename）务必保持 `id` 不变、子表引用不断。
- **先例**：迁移 070 已用 `batch_alter_table(recreate="always")` 重建过 agents 加 tenant/team FK——照搬该范式，降风险。
- users/tenants/teams 重建简单（被引用少），同 070/084/085 batch 范式。

## D4 — downgrade

- FK 部分可逆：downgrade 把四表 FK 的 ondelete 重建回 NO ACTION（含 users.tenant_id 回 legacy 形）。
- model_routes：downgrade 重建**空表** + 索引（schema 可逆），不恢复数据（drop 即弃数据，pre-launch 窗口可接受）。
- forward-only 原则下 downgrade 仅供本地回退，不用于生产数据恢复。

## D5 — 迁移编号

新迁移 append after head（当前 085 → 086，**勿硬编码** down_revision，apply 前 pull 确认真实 head；若期间有新迁移占号则顺延）。drop model_routes + 四表 FK 重建可在同一迁移文件内用清晰 helper（mirror 084 的 `_rebuild_*` 结构），或拆 086/087 两文件——以 apply 时可读性为准，但同属本 change。
