## Why

skill-admin-api 的 per-skill observability（命中次数、触发的 session）由 `engine_observability()` 占位符提供，永久返回 `{"hits": 0, "sessions": [], "stale": True}`。admin console 的 observability tab 因此永远显示陈旧空数据，运维无法看到哪些 skill 真正被使用、被哪些 agent 触发——侵蚀对管理台的信任，也无法支撑 skill 库的取舍决策。

## What Changes

- 新建 `skill_hits` 表（migration 057）：记录每次 `read_skill` 成功加载的命中（skill_name / agent_id / session_id / triggered_at）
- `skill_admin_store` 新增 `record_hit(...)` 写入命中、`observe(skill_name)` 聚合查询（hits 计数 + 去重 session 列表）
- `read_skill` 成功 `load()` 后 best-effort 记录命中（从 tool_context 取 agent/session；失败不阻断返回）
- `skill_admin_api.engine_observability` 改调 `skill_admin_store.observe`，返回真实数据（`stale: False`）

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-admin-api`：per-skill observability 返回真实命中/session 数据（替换 stale 占位符）

## Impact

- **新增文件**：`migrations/versions/057_add_skill_hits.py`、`tests/integration/test_skill_observability.py`
- **修改文件**：`src/fleetent/platform/skill_management/skill_admin_store.py`（record_hit / observe）、`src/fleetent/platform/skill_management/skill_admin_api.py`（engine_observability）、`src/fleetent/tools/builtin_tools.py`（read_skill 记录命中）
- **DB**：新表经 Alembic 管理；store 用 named params、不建表
- **无破坏性变更**：read_skill 记录是 best-effort（try/except，不阻断）；observe 返回结构在原占位符基础上填真实值
