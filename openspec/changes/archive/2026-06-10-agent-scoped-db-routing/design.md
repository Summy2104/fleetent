## Context

3b-1 把 3a 的 router/Y 地基泛化到 per-agent 粒度。设计已在讨论中定（router 结构 + 命名），本 doc 对齐真实代码 + 落 apply 策略。

现状（已核实）：
- 3a 的 `tenant_router.TenantRouter.scope(tenant) → KbScope{kb_db, kb_vector_backend}`，后端 `SQLiteTenantBackend.resolve` 已算 `<data_dir>/<tenant>/kb.db`。KB 形状，只 per-tenant。
- **session 是两套存储**：`session/manager.py` 的会话**内容是 JSON 文件**（`SESSIONS_DIR`）；`session/index.py` 的**元数据索引是 DB 表**（`sessions` 表 + `ensure_schema`，create_database 自连）。
- traces/memory/reflection/approvals 仍 `ensure_schema` 自建于全局 DB。

约束：per-agent 库走嵌入式 Y、非 alembic；不得 import platform；统一经 db.py/router 边界；上线前不迁移数据。

## Goals / Non-Goals

**Goals:**
- router 泛化为 `tenant_scope(tenant)` + `agent_scope(tenant, agent_id)` 两平级解析器；per-agent 库 `agent_state.db` / `agent_vectors.db`。
- session 元数据索引 DB 表迁入 per-agent `agent_state.db`（Y + agent_scope），作首个 per-agent 消费者。

**Non-Goals:**
- traces/memory/reflection/approvals 迁 Y（3b-2/3/4）；共享记忆（3c）；多主体 fan-out + 只读投影（3d）。
- session 内容 JSON 文件的 per-(tenant,agent) 路由（单机已在 agent home 下；多主体留 3d）——本切片只迁元数据 DB 表。
- per-agent 向量的真实消费（memory 向量在 3b-3 才接）；本切片 `agent_scope` 已**返回** `vector_backend` 句柄，但暂无消费者。

## Decisions

**D1 两个平级 typed 解析器，不嵌套。** `tenant_scope(tenant)` / `agent_scope(tenant, agent_id)`，返回类型不同（资源不同）。
- 备选：嵌套 `tenant(t).agent(a)`。否决——agent 请求本就同时已知 (tenant, agent_id)，平铺传参最简，嵌套徒增中间对象；且与 3a 的平的 `scope` 一脉相承。

**D2 `<tenant>/<agent_id>/` 包含关系沉进 `SQLiteTenantBackend`。** API 不暴露目录结构，路径只活在后端。
- 备选：调用点拼路径。否决——违反"调用点只表达作用域"。

**D3 命名 `agent_state.db` / `agent_vectors.db`。** 配对 `X.db`/`X_vectors.db`，per-agent 层 X=归属（agent）。`agent_state` 避免撞 runtime 引擎 / agent 定义。（data-model §5.7）

**D4 `scope` → `tenant_scope` 重命名。** 3a 的 `scope(tenant)` 改名 `tenant_scope`，与 `agent_scope` 成对。调用点（KB 侧）同步改。
- 备选：保留 `scope` 给 KB、只加 `agent_scope`。否决——两个解析器命名不对称，读着别扭；3a 刚落、调用点少，改名成本低。

**D5 session 第一个消费者 = 元数据 DB 表（非 JSON 内容）。** `session/index.py` 的表走 agent_state.db + Y；JSON 内容文件不在本切片。
- 理由：元数据索引是干净的"关系表 + ensure_schema"store，完美锚点，照搬 3a/KB 套路；JSON 内容是另一种存储机制（无 schema、不走 Y）。

**D6 单主体 `default` 先。** `agent_scope("default", agent_id)` → `<data_dir>/default/<agent_id>/`；多主体 fan-out 留 3d，调用点不变。

## Risks / Trade-offs

- **`scope`→`tenant_scope` 重命名漏改调用点。** → 缓解：全仓 grep + 类型检查；红/绿覆盖 KB 侧路由仍工作。
- **session 元数据与内容跨存储**（元数据进 agent_state.db、内容仍 JSON）。→ 这是现状的延续（本就两套），不引入新割裂；只是元数据的物理 home 变。文档写清，避免误解为"session 全进 DB"。
- **agent_scope 返回 vector_backend 但本切片无消费者**（memory 向量 3b-3 才接）。→ 句柄就位但不强制使用，降低后续接入摩擦；测试只验解析正确、不验向量消费。
- **与 #4 同改 agent_app**。→ apply 串行（proposal 已注）。

## Migration Plan（apply 分阶段，串行红绿）

1. router 泛化：`scope`→`tenant_scope` + 新增 `agent_scope` + `AgentScope` + 后端 per-agent 路径；同步 KB 侧调用点。
2. per-agent 库的 `MIGRATIONS`：把 `session/index.py` 的 DDL lift 进 per-agent 库迁移清单（v1）。
3. session 元数据连接走 `agent_scope` + migrate-on-open；`agent_app._init_agent_db_schema` session 部分接线。
4. 收尾：依赖护栏 + 既有 session/index 测试行为不变 + 门禁。

- 回滚：feat 分支；未上线、新库全新建，回滚 = revert。

## Open Questions

- 单机（standalone）下 `<data_dir>/default/<agent_id>/` 的两层嵌套是否对单 agent 部署过深？倾向接受（router 统一布局，单机退化无害）；实现时若想扁平可在后端特判，spec 不约束。
