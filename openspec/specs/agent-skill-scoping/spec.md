# agent-skill-scoping Specification

## Purpose
TBD - created by archiving change agent-skill-scoping. Update Purpose after archive.
## Requirements
### Requirement: agent 可声明 allowed_skills 收窄技能清单

agent 定义 SHALL 含一个 `allowed_skills` 列表（默认为空，向后兼容）声明该 agent 默认可见的技能子集。`allowed_skills` 仅决定哪些技能进入暴露给该 agent 的 `<available_skills>` 清单，SHALL NOT 构成能力授权边界。

#### Scenario: allowed_skills 字段持久化
- **WHEN** 以 `allowed_skills=["weather"]` 创建一个 agent
- **THEN** 该字段被持久化，读回该 agent 时 `allowed_skills == ["weather"]`

#### Scenario: 默认空列表
- **WHEN** 创建 agent 时未声明 `allowed_skills`
- **THEN** 该 agent 的 `allowed_skills` 默认为空列表

### Requirement: 空 allowed_skills 不限制（向后兼容）

当 agent 的 `allowed_skills` 为空或未提供（None）时，技能清单渲染 SHALL NOT 施加任何收窄——所有当前已启用（未被任一禁用来源排除）的技能照常出现在清单中，行为与未引入该字段时一致。

#### Scenario: 空 allowed_skills 全部已启用技能可见
- **WHEN** 渲染技能清单时 `allowed_skills` 为空列表
- **THEN** 所有已启用技能都出现在 `<available_skills>` 清单中，与现状一致

#### Scenario: None 等同于空
- **WHEN** 渲染技能清单时未传 `allowed_skills`（None）
- **THEN** 不施加收窄，所有已启用技能可见

### Requirement: 非空 allowed_skills 收窄清单

当 agent 的 `allowed_skills` 非空时，技能清单 SHALL 只保留名字在 `allowed_skills` 中的技能；未列出的技能 MUST NOT 出现在该 agent 的 `<available_skills>` 清单中。

#### Scenario: 只渲染所列技能
- **WHEN** `allowed_skills=["weather"]` 且已启用技能含 `weather` 与 `billing`
- **THEN** 清单只含 `weather`，不含 `billing`

#### Scenario: 未列出的技能被排除
- **WHEN** 某已启用技能的名字不在 `allowed_skills` 中
- **THEN** 该技能不出现在该 agent 的清单中

### Requirement: allowed_skills 收窄与技能禁用叠加

allowed_skills 收窄 SHALL 与既有技能禁用谓词叠加（逻辑与）：仅当一个技能名命中 `allowed_skills`（或 `allowed_skills` 为空表示不约束）**且**未被任一禁用来源（`audit_blocked` / `frontmatter_disabled` / `config_disabled` / `default_disabled`）排除时，才进入清单。禁用 SHALL 优先于收窄——被禁用的技能即便在 `allowed_skills` 中也 MUST NOT 出现。

#### Scenario: 被禁用的技能即使在 allowed_skills 中也不出现
- **WHEN** `allowed_skills` 含 `weather`，但 `weather` 被某禁用来源排除
- **THEN** `weather` 不出现在清单中（禁用优先于收窄）

#### Scenario: 命中且未被禁用才出现
- **WHEN** `allowed_skills` 含 `weather` 且 `weather` 未被任何来源禁用
- **THEN** `weather` 出现在清单中

### Requirement: allowed_skills 仅作用于清单可见性，非授权边界

allowed_skills SHALL 只过滤 `<available_skills>` 清单的渲染输出，MUST NOT 改变工具访问控制（`allowed_tools` / `check_tool_access`），亦 MUST NOT 阻止按名加载技能内容（`read_skill` 的显式 `load`）。被收窄掉的技能默认不出现在清单、模型不会主动读取它，但按名 `load` 行为与既有「load 不受禁用约束」口径一致，保持不变。

#### Scenario: 收窄不改变工具访问控制
- **WHEN** 某技能被 `allowed_skills` 收窄排除
- **THEN** 工具访问控制（`allowed_tools` 白名单与风险审批门）不受影响，工具授权判定不变

#### Scenario: 按名 load 不受收窄约束
- **WHEN** 一个技能不在某 agent 的 `allowed_skills` 中
- **THEN** 它不出现在该 agent 的清单中，但按名 `load`（`read_skill`）该技能仍能返回其内容，与既有禁用不挡 load 的口径一致

### Requirement: run 与 run_stream 透传 allowed_skills

agent 运行入口 `run()` 与 `run_stream()` SHALL 接受一个 `allowed_skills` 参数（默认 None），并在构建技能清单的位置将其传给清单渲染；调用方 SHALL 从 agent 定义取 `allowed_skills`（无 agent 绑定时为 None，不收窄）。

#### Scenario: 流式路径透传 agent 的 allowed_skills
- **WHEN** 经 `run_stream` 处理一条绑定了 `allowed_skills=["weather"]` 的 agent 的消息
- **THEN** 渲染出的清单只含 `weather`（其余已启用技能被收窄）

#### Scenario: 无 agent 绑定不收窄
- **WHEN** 一条消息没有绑定任何 agent（`allowed_skills` 为 None）
- **THEN** 清单不施加收窄，所有已启用技能可见

### Requirement: Managed skill file deployment is node-owned

In managed mode, platform SHALL project skill visibility decisions into agent config and desired-state, but node SHALL be the component that writes skill files into the agent home. Agent runtime SHALL read only the tenant-aware local skill copy under its home.

#### Scenario: Allowed skills remain config-driven
- **WHEN** an agent has explicit skill bindings
- **THEN** generated agent config contains the corresponding `allowed_skills`
- **AND** runtime uses that config to build its catalog

#### Scenario: Node writes the local skill copy
- **WHEN** desired-state includes skill `foo` for tenant `acme` agent `bot`
- **THEN** node writes files under `tenants/acme/agents/bot/skills/foo/`
- **AND** platform does not write those files directly in managed mode

#### Scenario: Runtime reads local copy only
- **WHEN** the agent runtime loads skill `foo`
- **THEN** it reads from its own home `skills/foo/`
- **AND** it does not read the public skill pool or platform management DB

