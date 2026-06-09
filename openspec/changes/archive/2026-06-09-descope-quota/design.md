## Context

`usage-quota` 经核实是非功能半成品:`governance/quota.py` 逻辑齐全,但 `check_quota`/`record_usage` 全仓零调用,`server.py::_emit_over_quota_event` 仅 `logger.warning` 桩。`quotas`/`quota_usage` 表由 `quota._init_db` 运行时自建(不在 alembic)。chore 性质删除,无行为变更(本就没强制 quota)。

## Goals / Non-Goals

**Goals**：删 `quota.py` + `_emit_over_quota_event` 桩 + `quotas`/`quota_usage` 表 + `usage-quota` capability。

**Non-Goals**：不碰请求路径/loop/token 计量;不动其他治理(permission_gate/blocklist/audit/user_store)。

## Decisions

**D1：表用 `DROP TABLE IF EXISTS` 迁移清理。** 因表是运行时 `_init_db` 自建(不在 alembic),fresh alembic 库本无此表,但已部署库可能有 → `DROP ... IF EXISTS` 幂等清理。downgrade 按 `quota._init_db` 原 DDL 重建以保可逆。

**D2：删 quota.py 前 grep 兜底。** 确认无 `import fleetent.governance.quota` / `check_quota` / `record_usage` / `set_quota` 的非测试调用点(已核实仅自身与 server 桩)。

## Risks / Trade-offs

- **[残留导入]** → D2 二次 grep;若有"仅测 quota"的测试,随之删除。
- **[迁移可逆]** → `DROP IF EXISTS` + downgrade 重建;空库 upgrade→downgrade→upgrade 往返通过(downgrade 重建、upgrade 再 drop)。
- **[行为回归]** → 无:quota 本就未强制,删除不改任何请求行为;跑 server 启动 + /chat 既有测试确认无回归。
