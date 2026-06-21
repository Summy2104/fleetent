> **状态:占位 / BLOCKED — 仅登记范围,不在当前批次实施。** 触发判据:**部署真走分布式 + 有网络DB/多机环境可端到端验证**。详见 [target-architecture.md §12](../../../docs/architecture/target-architecture.md) 与 [roadmap](../../../docs/roadmaps/kb-memory-substrate-roadmap.md)。

## Why

`substrate-backend-abstraction`(B1)立了可插拔后端抽象 + 本地 SQLite 后端。B2 在该抽象下实现**网络托管后端**(Postgres + Qdrant 等,self-hostable,数据不出内网),使 agent 侧 per-tenant 数据(memory/KB/sessions/向量)在**分布式部署**(agent host ≠ ingest/写入方)下可经网络共享访问。

**为什么现在只占位不实施**:**没有分布式/网络DB 环境可端到端验证它**。按"实施了能确保整套机制正常运转"的标准,B2 现在**无法满足**——构建出来也只是"看着对、跑不了真验证"。等真有目标环境(网络 DB + 多机)再展开。

## What Changes（占位,不在本批实施）

- 在 B1 的 `BaseSubstrateBackend` 下实现网络后端:关系数据 → Postgres;向量 → Qdrant(对齐已有可换向量层)。按 `postgresql://` / Qdrant URL scheme 经工厂选型。
- 网络后端的迁移模型(非嵌入式 SQLite forward-only;Postgres 上怎么跑 schema 演进)。
- 多租户路由 / 连接池 / 连接配置(kb-worker、agent、memory 的"底座连接"填网络 URL)。
- `connector-cred-job-ref`:job 带凭据 ref、worker 运行时按 ref 从 Vault 解析(分布式下 secret 不在队列 at-rest 的配套;Vault 已实现,这块相对可验证,可随 B2 或单独小 change 先做)。

## Capabilities

### New Capabilities
<!-- 待有环境、终局形态定后定义;可能拆为:Postgres 关系后端 / Qdrant 向量对齐 / 迁移模型 / connector-cred-job-ref 多个 change -->

## Impact

- **BLOCKED ON / 前置**:`substrate-backend-abstraction`(B1)落地 + 部署走分布式 + 有网络DB/多机环境可验证。
- **触发判据**:agent 与 ingest/写入方不再共享文件系统(单机→分布式)。单机/dev 永远保留本地 SQLite 后端。

## 待讨论决策点（远期,有环境时拍）

1. 关系后端选型与版本(Postgres?)、向量后端(Qdrant?已部分支持)。
2. 网络后端的 schema 迁移模型(Alembic on Postgres?嵌入式不再适用)。
3. 多租户在网络后端的物理/逻辑隔离(per-tenant DB / schema / row-level?)与连接池、路由。
4. `connector-cred-job-ref` 的 Vault 接入授权范围(worker principal 能解析哪些 tenant 的凭据 ref)。
