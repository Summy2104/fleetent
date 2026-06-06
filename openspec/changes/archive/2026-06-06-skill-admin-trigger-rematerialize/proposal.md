## Why

Change `skill-materialize-db-fields` 让 materialize 能把 skill 管理决策写入 agent.yaml，但 admin 的 skill 写操作（全局 disable/enable、per-agent 绑定）只写 DB，从不触发 re-materialize。结果是：管理台改了 skill 状态，agent.yaml 仍是旧的，必须等下一次手动 materialize 才生效。这一步补上"写 DB → 自动刷新受影响 agent 的 agent.yaml"的链路。

## What Changes

- `agent_store` 新增 `list_all_names() -> list[str]`，列出所有已 authored agent 的名字
- `materialize` 新增 `rematerialize_all() -> list[str]`，对所有 agent 重新导出 agent.yaml（best-effort，单个失败不阻断其余）
- `skill_admin_api` 的三个写接口在写 DB 后触发 re-materialize：
  - `disable_skill` / `enable_skill`：全局状态变化影响所有 agent → `rematerialize_all()`
  - `set_skill_agent_binding`：只影响该 agent → `materialize_from_store(agent_name)`（用 `get_agent_name_by_id` 解析 name）

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-admin-api`：明确全局 enable/disable 与 per-agent 绑定写操作后必须触发受影响 agent 的 re-materialize

## Impact

- **修改文件**：
  - `src/fleetent/agent_store.py`（新增 `list_all_names`）
  - `src/fleetent/platform/agent_lifecycle/materialize.py`（新增 `rematerialize_all`）
  - `src/fleetent/platform/skill_management/skill_admin_api.py`（三个接口接入触发）
- **测试**：`tests/unit/` + `tests/integration/`
- **无破坏性变更**：re-materialize 是幂等的 best-effort 操作；接口返回值保持不变
