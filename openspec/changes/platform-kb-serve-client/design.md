## Context

平台 `/admin/kb/*` 现进程内直读 KB 库（`kb_engine_*`/`kb_search` 经 TenantRouter），只在平台与 KB 同机时成立。目标拓扑：KB 单机中心、平台 1:1 可异机 → 平台须退成 kb-serve HTTP 客户端。Change A 已给 kb-serve 补全数据面端点；Change C 让 kb-serve 多租户（一个端点、principal 路由）。B 把平台数据面切到 kb-serve。绑定（agent_kbs@management.db）+ observation（跨 agent trace）搬不走，仍平台自持。

## Goals / Non-Goals

**Goals**
- 平台 KB 数据面（CRUD/文档/检索/评估）经中心 kb-serve HTTP，不再 in-process 直读 → 支持平台与 KB 分机。
- `/admin/kb/search` 经 kb-serve 得 rerank/planner + 对齐契约。

**Non-Goals**
- 不动绑定 / observation（平台自持，搬不走）。
- 不动 kb-serve/worker（C）、agent 侧（D）。
- 平台 RBAC/session 鉴权保持在平台层。

## Decisions

**D1：新增平台侧 kb-serve 客户端。** 一个 HTTP 客户端封装 Change A 补的 kb-serve 端点（search/kb CRUD/documents/eval）。平台持中心 kb-serve URL（平台配置新增项）+ 共享 service key（引用）。每次调用**为目标租户 mint principal**（`identity` 的 principal 编码 + `X-Fleetent-Principal` header）+ Bearer 共享 key。因 C 是**一个多租户 kb-serve**,平台只需一个 URL、tenant 靠 principal，零 per-tenant 扇出。

**D2：改写数据面 handler 走客户端。** `kb_engine_list/create/edit/archive`、`kb_search`、documents/chunks/删文档、evaluations 从调 `kb_management_runtime.*` / in-process 改为调 kb-serve 客户端。`/admin/kb/search` 请求体对齐 kb-serve（`limit` 替 `top_k`、透传 `rerank`/`use_planner`），响应对齐 KnowledgeChunk（`id` 而非 `chunk_id`）。

**D3：绑定 + observation 保持 in-process。** `/admin/kb/{id}/agents`、`/admin/agents/{name}/kbs`（agent_kbs_store @ management.db）与 `/admin/kb/{id}/observation`（`kb_observation.aggregate` 需 bound_agent_ids + 跨 agent trace）**不改**——它们本就是平台控制面数据，kb-serve 拿不到。绑定操作与 KB 数据面操作在一个 handler 里协作时（如建 KB 后绑定），KB 部分走 kb-serve、绑定部分走 in-process，平台编排。

**D4：鉴权分层。** 平台入口仍 session + RBAC（viewer/admin）；通过后平台**以服务身份**用共享 service key + mint 的租户 principal 调 kb-serve。kb-serve 的 service-key 只是传输门（C 的模型），真实操作者/租户由平台 mint 的 principal 承载。

## Risks / Trade-offs

- **平台新增对 kb-serve 的运行时依赖** → 平台管理 KB 需 kb-serve 可达；kb-serve 挂则 KB 管理降级（绑定/observation 仍可，因 in-process）。可接受（kb-serve 中心高可用）。
- **`/admin/kb/search` 响应形状变化** → 前端 playground 未消费（Tier-3 未建），无破坏；未来建 UI 时按 kb-serve 契约。
- **依赖 C 落地形状**（URL/鉴权/多租户路由）→ gated on C；apply 先核 C 实现。
- **编排型 handler（KB+绑定）** → 明确拆两段（KB 走 HTTP、绑定走 in-process），事务性弱化（跨两侧无强事务）——建 KB 后绑定失败需可重试/幂等；apply 时保证幂等语义。

## Migration Plan

无数据迁移。平台配置加中心 kb-serve URL + 共享 service key 引用。回滚 = revert（回落 in-process 直读，仅平台与 KB 同机时可用）。

## Open Questions

无（URL/鉴权字段在 apply 时对齐 C 落地）。
