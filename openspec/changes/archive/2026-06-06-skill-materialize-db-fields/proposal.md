## Why

Platform 的 skill 管理决策（全局 disable、per-agent 绑定）写入 DB（`skill_admin_state`、`agent_skills`），但 `materialize.py:agent_file_from_store()` 从不读这两张表——它只把 `agent.allowed_skills`（authored 值）写入 agent.yaml。结果是：管理台禁用某 skill、或在绑定矩阵中为 agent 开关 skill，全都不会反映到 agent 运行时。这是 platform→agent 解耦架构下数据流的断点：agent 只读 agent.yaml，而 materialize 没把 DB 决策落到 agent.yaml。

## What Changes

- `agent_file_from_store()` 读取 `skill_admin_store.list_states()`，把 `global_enabled=0` 的 skill 名汇集到 `AgentFile.disabled_skills`
- `agent_file_from_store()` 读取 `skill_admin_store.enabled_skill_names(str(agent.id))`：当该 agent 有绑定行时，用绑定的 enabled 子集覆盖 `allowed_skills`；无绑定行时回退到 authored 的 `agent.allowed_skills`

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-agent-binding`：明确 materialize 必须把 `agent_skills` 绑定矩阵转换为 agent.yaml 的 `allowed_skills`，并定义无绑定时的回退
- `platform-agent-lifecycle`：明确 materialize 必须把全局 disabled skills 写入 agent.yaml 的 `disabled_skills`

## Impact

- **修改文件**：`src/fleetent/platform/agent_lifecycle/materialize.py`（`agent_file_from_store()` 函数）
- **依赖**：`skill_admin_store.list_states()` 和 `enabled_skill_names()`（已存在）
- **测试**：`tests/integration/`（真实 DB，验证 materialize 输出 yaml 的 `disabled_skills` / `allowed_skills` 正确）
- **无破坏性变更**：无绑定、无全局 disable 的 agent 行为不变（回退到 authored 值）
