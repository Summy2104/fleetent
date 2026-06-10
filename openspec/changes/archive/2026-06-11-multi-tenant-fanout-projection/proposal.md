## Why

持久层 #3 的收口切片 **3d**：① 打开**多主体 fan-out**（前序切片都"单主体 default 先"，本切片让路由按**真实主体**展开到 `<tenant>/` 目录，兑现"A/B 主体物理隔离"的合规硬要求）；② 落地 **platform 只读投影**（target-arch §7 的实现）——让控制面只读地观测前序切片落到 agent 侧各物理库的状态。是整个 #3 物理拓扑的合拢。

> 依赖：3a + 3b-1/2/3/4 + 3c（所有库已 router 化、单主体可跑）+ `sqlite-wal-concurrency`（只读/写并发）。多主体要在 Pilot 即用，故本切片必须上线前到位。

## What Changes

- **多主体 fan-out**：路由的主体来源从硬编码 `default` 改为 **agent 的归属主体**（agent 配置 `tenant_id`（`agent_tenant`），来自 agent 配置/materialize）；`tenant_scope`/`agent_scope` 据此路由到 `<tenant>/...`。解除前序"单主体先行"限制。
- **主体目录 provisioning**：platform 在 onboard 主体/agent 时建立 `<tenant>/`、`<tenant>/<agent_id>/` 结构（或首次开库 lazy 建）；归 `platform/agent_lifecycle`。
- **platform 只读投影（§7 实现）**：router 提供**只读模式**句柄；platform 经**共享 store 读函数 + 只读连接**读 agent 侧库，经 `management.db` registry 发现并遍历聚合；**不物化副本、不要求 agent 反向写**。approvals 投影 join 身份（#4）；memory 跨 agent 遍历；shared/KB per-tenant 直读。

不在本切片：跨主体共享 KB（主体内 M:N 已足，见 §5.7）；非 SQLite 后端实现（PG/RLS 由"可换后端"另行）。

## Capabilities

### New Capabilities
- `platform-read-projection`: 控制面只读观测 agent 侧物理库的统一机制——只读 router 句柄 + 共享 store 读函数 + registry 发现/遍历聚合；禁物化副本/禁 agent 反向写（target-arch §7 落地）。

### Modified Capabilities
- `tenant-scoped-db-routing`: 解除"单主体先行"——`tenant_scope`/`agent_scope` 按 agent 归属主体（agent 配置 `tenant_id`（`agent_tenant`））多主体 fan-out 到 `<tenant>/` 物理分区；新增主体目录 provisioning。

## Impact

- **代码**：`tenant_router`/`SQLiteTenantBackend`（多主体路径，去 default 硬编码）；`platform/agent_lifecycle`（provisioning）；platform 各 console/统计读侧改走只读 router + 读函数；router 加只读模式。
- **数据/schema**：建立 per-主体目录结构；上线前不迁移数据（fresh build）。
- **约束**：platform → 只读 agent 库（允许方向）；agent ✗→ platform；agent 物理够不到别主体。
- **依赖**：全部前序 #3 切片 + `sqlite-wal-concurrency`；approvals 身份富化依赖 #4。
- **文档**：data-model.md §5.7（物理分区/17 库/命名）、target-architecture-proposal.md §7（只读投影模型）。
