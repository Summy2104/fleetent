> **状态：占位 / BLOCKED — 终局形态未定，依赖阶段1~5 完成**。本 change 不在当前批次实施，仅登记范围与前置条件，待前序重构落地且终局形态决策后再展开。

## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段6（后置）**。当 `knowledge_base/` 已是顶层独立组件、读写边界清晰（阶段2 完成）后，可进一步把它升格为**独立的自托管服务**：对外暴露检索 API（数据面，被 agent runtime 消费）+ 管理 API（控制面，被 platform 消费）。这与 fleetent「基础设施组件可自托管、数据不出内网」的原则一致——KB 像 PostgreSQL/Qdrant 一样是个可独立部署的组件。

## What Changes（占位，不在本批实施）

- knowledge_base 组件升格为独立服务进程：检索 API（search/graph_search）+ 管理 API（ingest/connector/KB CRUD/调度/运维数据）。
- agent runtime 依赖"检索客户端"，platform 依赖"管理客户端"，两者都不再直接 import KB 内部。
- self-hostable，符合 on-prem 数据主权。

## Capabilities

### New Capabilities
<!-- 待终局形态决策后定义 -->

## Impact

- **BLOCKED ON**：阶段1（vector_store）、阶段2（KB 组件+读写边界）、阶段3/4（intelligence 解散）、阶段5（护栏+CLAUDE.md）全部完成。
- **前置决策（纲领 §9 Open Questions）**：终局形态——单体内包边界 vs 独立服务进程；单机 agent（无 platform）的摄取单元形态（ingest CLI vs KB 服务 sidecar）。

## 待讨论决策点（远期）

1. 终局形态：是否真的抽独立进程，还是单体内组件边界已足够（封装强度按需升级）。
2. 检索 API / 管理 API 的协议（HTTP？gRPC？进程内接口）。
3. 单机部署形态：agent + KB 服务如何共部署，数据主权如何保证。
4. 与现有 `platform/knowledge_base_management` 的客户端关系。
