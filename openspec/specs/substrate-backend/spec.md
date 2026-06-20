# substrate-backend Specification

## Purpose
Define the pluggable relational substrate backend abstraction for agent-side stores so local SQLite remains the default while future network backends can be added behind the same `db.py` boundary.

## Requirements
### Requirement: 可插拔底座后端抽象
系统 SHALL 提供 agent 侧数据底座的可插拔后端抽象：一个后端基类/Protocol（`BaseSubstrateBackend` 或等价）+ 能力声明（`SubstrateCapabilities`，如 `network` / `shared_across_hosts` / `embedded_migrations`）+ 工厂（按连接 URL scheme 选实现）。消费方 SHALL 按 capabilities 门控行为，SHALL NOT 用 `isinstance` 判后端类型（对齐 sandbox backend 范式）。

#### Scenario: 按 URL scheme 选后端
- **WHEN** 以 `sqlite://` 或本地路径 URL 请求底座
- **THEN** 工厂返回本地 SQLite 后端实例

#### Scenario: 能力门控而非类型判断
- **WHEN** 某路径仅适用于具备某能力的后端
- **THEN** 消费方查 `SubstrateCapabilities` 标志门控
- **AND** 不写 `isinstance(backend, SQLite...)`

### Requirement: 本地 SQLite 后端为默认实现，行为不变
现有 `SQLiteDatabase` + 嵌入式 forward-only 迁移（migrate-on-open + `PRAGMA user_version`）SHALL 收编为本地 SQLite 后端实现，作为默认。开库结果、迁移行为、PRAGMA 与现状 SHALL 完全一致（单机现有 integration 行为不回退）。

#### Scenario: SQLite 后端开库与迁移不变
- **WHEN** 经工厂以本地 URL 开 per-agent / 共享记忆 / KB 关系库
- **THEN** 得到的库、其嵌入式迁移与 PRAGMA 行为与改造前一致

### Requirement: agent 侧关系库经工厂开库
per-agent 运行库（`agent_state.db`）、共享记忆库（`shared_memory.db`）、KB 关系库（`kb.db`）的开库 SHALL 经底座工厂获取后端，而非直接构造 `SQLiteDatabase`。底座抽象层 SHALL NOT 引入 store → `fleetent.platform.*` 反向依赖（护栏）。

#### Scenario: 三关系库统一经工厂
- **WHEN** runtime / memory / knowledge_base 打开各自 per-tenant 关系库
- **THEN** 均经 `create_substrate(url)`
- **AND** 不直接 `SQLiteDatabase(path=...)`

#### Scenario: 抽象层不破坏边界护栏
- **WHEN** 运行 `test_module_dependency_guardrails`
- **THEN** 底座抽象未引入 agent 侧 / 组件 → platform 的反向 import
