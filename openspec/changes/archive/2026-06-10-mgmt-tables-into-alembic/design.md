## Context

`db-migration` 已要求管理表只经 alembic,但 4 张管理表(`api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist`)仍用 store `_init_db` 自建——违规。本变更收编它们,完成管理库 alembic 单权威(`users` 已在 #2.5 收编)。机械、与 #2.5 收编 users 同模式、无业务行为变更。

## Goals / Non-Goals

**Goals**:4 张管理表入 alembic + 各 store 去 `_init_db` + 启动门覆盖;`im_channel_allowlist` 去重(若有)。

**Non-Goals**:
- `approvals` 的 alembic 孤立定义(001/060)退场 → **留 #3**(与 approvals 物理落点一起)。
- agent-side 表(走嵌入式迁移 Y,§5.2)——本就不进 alembic,不碰。
- 其余已 descope/删的表(quotas/invites 等)——已在减法处理。

## Decisions

**D1:迁移用 `CREATE TABLE IF NOT EXISTS`(onboard 既有表)。** fresh alembic 库由迁移建出;已部署库(表已由旧 `_init_db` 建)则 no-op、不破坏数据。与 #2.5 收编 users 一致。

**D2:store 删 `_init_db` 建表逻辑。** 4 个 store 模块不再自建表(改依赖 alembic 已就绪);保留它们的 CRUD/查询(经 db.py runtime、named params)。

**D3:不动 approvals。** 它现 agent 侧(approval_store)、alembic 还有 001/060 的孤立定义——退场与 approvals 物理位置耦合,留 #3 一起。

## Risks / Trade-offs

- **[迁移幂等]** → `IF NOT EXISTS` + 在"已有这些表的库"上跑往返通过;不丢既有数据。
- **[启动门]** → 去 `_init_db` 后部署须先 `upgrade head`;部署文档/启动检查须明确(#2.5 已为 users 立同门,本期统一覆盖管理表)。
- **[列定义须与旧 `_init_db` 一致]** → 迁移建表的列须逐字对齐各 store 原 `_init_db` 的 DDL,避免 fresh 库与旧库 schema 漂移;迁移前比对。
- **[im_channel_allowlist 重复 CREATE]** → 核查源码是否真有两处,去重为单一(经 alembic)。
