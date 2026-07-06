## Why

平台 `/admin/kb/*` 现在**进程内直读写 KB 库**（`kb_engine_list/create/edit/archive`、`kb_search` 经 `TenantRouter` in-process）。这只在**平台与 KB 同机**时成立。但目标拓扑下 KB 是单机中心服务、平台与它 **1:1 但可异机**（见 [[kb-service-multi-tenant]]）——平台异机时 in-process 直读**够不到 KB 库**。且平台的 `/admin/kb/search` 是 kb-serve 检索的**能力缩水子集**（无 rerank/planner）+ 契约漂移。

本 change（收口程序 **B**）让**平台 KB 数据面退成 kb-serve HTTP 客户端**：CRUD/文档/检索/评估经中心 kb-serve（Change A 已补全这些端点），平台不再进程内直读 KB 库。**绑定（agent_kbs）与 observation 仍平台自持**（依赖 management.db / 跨 agent trace，kb-serve 拿不到）。副作用：`/admin/kb/search` 经 kb-serve 后**自动获得 rerank/planner + 对齐契约**，消除缩水+漂移。

**前置**：gated on Change C（多租户 kb-serve 单端点 + 共享 service-key）——因是**一个多租户 kb-serve**，平台打**一个 URL**、tenant 放 principal，零扇出。apply 时对齐 C 落地的地址/鉴权。

## What Changes

- **平台 kb-serve 客户端**：新增平台侧 kb-serve HTTP 客户端（覆盖 Change A 补的 kb-serve 端点：`/search`、`/kb` CRUD、`/kb/{id}/documents[/chunks]`、`DELETE doc`、`/evaluations`）。平台持中心 kb-serve URL（配置）+ 共享 service key，为目标租户 mint principal（`X-Fleetent-Principal`）。
- **改写 `/admin/kb/*` 数据面 handler**：`kb_engine_list/create/edit/archive`、`kb_search`、documents/chunks/删文档、evaluations → 由 in-process 改为**调 kb-serve 客户端**。`/admin/kb/search` 请求/响应对齐 kb-serve（`limit`/字段名/KnowledgeChunk），并透传 `rerank`/`use_planner`。
- **绑定 + observation 不动**：`/admin/kb/{id}/agents`、`/admin/agents/{name}/kbs`（agent_kbs @ management.db）与 `/admin/kb/{id}/observation`（跨 agent trace 聚合）**仍平台 in-process**。
- 平台 RBAC（viewer/admin）+ session 鉴权仍在平台层，鉴权通过后再以共享 key 调 kb-serve。

**不做**：kb-serve/worker 多租户化（C）；agent 侧（D）；绑定/observation 迁移（本就搬不走）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-admin-api`：平台 KB **数据面**（列/建/改/归档 KB、文档列/预览/删、检索、评估）SHALL 经**中心 kb-serve HTTP 客户端**执行（不再进程内直读 KB 库），以支持平台与 KB 分机;`/admin/kb/search` 经 kb-serve 支持 rerank/planner 并对齐契约。绑定与 per-KB observation SHALL 仍由平台 in-process 承载（依赖 management.db / 跨 agent trace）。

## Impact

- **代码**：新增平台侧 kb-serve 客户端模块（`platform/knowledge_base_management/` 下）；改写 `kb_admin_api.py` 的数据面 handler（`kb_engine_*`/`kb_search`/documents/eval → HTTP）；平台配置加中心 kb-serve URL + 共享 service key 引用。
- **不改**：绑定 handler、observation 聚合（`kb_observation`）、`agent_kbs_store`。
- **spec**：`kb-admin-api` delta。
- **无迁移、无 schema 变更**；`/admin/kb/search` 响应形状变化（对齐 kb-serve）——前端 playground 未消费（Tier-3 未建），无破坏。
- 依赖：**gated on Change C**；与 Change D（agent 侧）**无文件重叠，可并行**。
