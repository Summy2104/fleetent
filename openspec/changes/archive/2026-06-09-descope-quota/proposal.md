## Why

`usage-quota` 能力是**非功能态的半成品**:`governance/quota.py` 的 `check_quota`/`record_usage` **全仓零调用**——请求路径不调 check_quota(超额不拒)、回合后不调 record_usage(用量不记);`server.py` 的 `_emit_over_quota_event` 只是一条 `logger.warning` 桩、也无调用者;无 admin 配置端点。spec 要求"超额返回 429",实现完全没接。

v1 不做用量配额(控成本/防滥用的需求出现时再完整做——届时要接请求入口 + token 计量 + admin 配置,且应在 **platform 入口**强制以避免 agent→platform 耦合)。本变更移除这套未接线的半成品。

## What Changes

- **删除** `src/fleetent/governance/quota.py`(set_quota/record_usage/check_quota 等)。
- **删除** `server.py` 的 `_emit_over_quota_event` 桩。
- **删除** `quotas` / `quota_usage` 两表:它们由 `quota._init_db` 运行时自建(不在 alembic);新增一条 `DROP TABLE IF EXISTS` 迁移清理已部署库中的残留,downgrade 按原 DDL 重建以保可逆。
- **移除** `usage-quota` capability(REMOVE 其 2 条 requirement)。

> 不在范围:任何请求路径/loop/计量改动(本变更只做减法,不接线)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
（无）

### Removed Capabilities
- `usage-quota`: 移除"per-user/global 配额"与"超额请求被拒"两条 requirement(实现从未接线;v1 descope)。

## Impact

- **代码**：删 `governance/quota.py`;删 `server.py::_emit_over_quota_event`。删前 grep 确认无 `import ...quota` / `check_quota` / `record_usage` 调用点(已核实仅自身与桩)。
- **迁移**：新增 `DROP TABLE IF EXISTS quotas; DROP TABLE IF EXISTS quota_usage`(downgrade 重建)。
- **specs**：移除 `usage-quota`。
- **测试**：删/改引用 quota 的测试。
- **零影响**：请求闭环不变(本就没强制 quota);agent runtime、其他治理(permission_gate/blocklist/audit)不动。
