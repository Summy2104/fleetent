## ADDED Requirements

### Requirement: KB 数据面经中心 kb-serve 客户端

平台 `/admin/kb/*` 的 **KB 数据面操作**(列/建/改/归档 KB、文档列/预览 chunk/删文档、检索、离线评估)SHALL 经**中心 kb-serve 的 HTTP 客户端**执行,SHALL NOT 进程内直读写 KB 库——以支持平台与 KB 分机部署(平台 1:1 于 KB 但可异机)。平台 SHALL 持中心 kb-serve URL(平台配置)与共享 service key(引用),每次调用为目标租户 mint `X-Fleetent-Principal` + Bearer 共享 key;因 kb-serve 多租户,平台打**一个 URL**、tenant 靠 principal 路由。

`/admin/kb/search` SHALL 经 kb-serve 检索,支持 `rerank` / `use_planner` 透传,请求/响应契约对齐 kb-serve(`limit`、KnowledgeChunk 形状)。

绑定(`/admin/kb/{id}/agents`、`/admin/agents/{name}/kbs`,agent_kbs @ management.db)与 per-KB `observation`(需 bound_agent_ids + 跨 agent 检索 trace)SHALL 仍由平台 in-process 承载,不经 kb-serve(kb-serve 无 agent/绑定/trace 概念)。平台入口鉴权(session + viewer/admin RBAC)SHALL 保持在平台层,通过后再以服务身份调 kb-serve。

#### Scenario: 平台数据面经 kb-serve
- **WHEN** admin 经平台 `/admin/kb` 列/建/改/归档 KB 或列/删文档或检索
- **THEN** 平台经中心 kb-serve HTTP 客户端执行(带共享 key + 为该租户 mint 的 principal),不进程内直读 KB 库
- **AND** 平台与 KB 分机时仍可用

#### Scenario: search 透传质量参数并对齐契约
- **WHEN** `/admin/kb/search` 带 `rerank=true` 或 `use_planner=true`
- **THEN** 平台经 kb-serve 检索、返回对齐 kb-serve 的 KnowledgeChunk 结果(不再是无 rerank/planner 的缩水子集)

#### Scenario: 绑定与 observation 仍平台自持
- **WHEN** 审视绑定端点与 `/admin/kb/{id}/observation`
- **THEN** 它们仍由平台 in-process 承载(agent_kbs @ management.db / 跨 agent trace 聚合),不经 kb-serve
