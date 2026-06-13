# plane-boundary-guardrails Delta

## ADDED Requirements

### Requirement: agent 标识键守护
身份模型（见 `docs/architecture/agent-identity-model.md`）的两条键规则 SHALL 由守护测试强制：① 平台关系表对 agent 的引用 MUST 为 `agent_id`（INTEGER，FK→agents.id）——**唯一例外是 `agents.name` 列本身**，agent name MUST NOT 出现在其它平台表；② agent 侧（agent_state.db / 物理产物 / 配置）对 agent 的标识 MUST 用 name，MUST NOT 出现 agent id（含列名）。name↔id 翻译 MUST 只在 materialize（写）与 read-projection（读）两个边界发生。

#### Scenario: 平台关系表无 agent name 列（除 agents）
- **WHEN** 扫描管理库各表的 agent 引用列
- **THEN** 除 `agents.name` 外不存在以 agent name 引用 agent 的列；引用一律为 `agent_id` INTEGER FK

#### Scenario: agent 侧无 agent id 标识
- **WHEN** 扫描 agent_state.db 列名与 agent 侧产物
- **THEN** agent 标识一律为 name（如 `traces.agent_name`），不存在叫 `agent_id` 或存平台整数 id 的 agent 标识

#### Scenario: 翻译只在两边界
- **WHEN** 扫描 name↔id 翻译的代码点
- **THEN** 仅出现在 materialize（id→name 盖产物）与 read-projection（name→id 关联）两处
