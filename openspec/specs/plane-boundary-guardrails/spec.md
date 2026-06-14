# plane-boundary-guardrails Specification

## Purpose

以 CI 强制护栏固化"核 + 4面"架构的依赖方向契约：核模块集合不依赖任何面命名空间、各面之间不互相直接依赖、reflection 两拆收口方向受护栏约束、audit_log 归顶层基座而非业务能力树。
## Requirements
### Requirement: 核模块不依赖面模块

核模块集合（`runtime` / `session` / `model` / `tools` / `integrations` / `governance` / `memory` / `long_term_ctx` / `reflection` / `skills` / `knowledge_base.retrieval`）中任一模块 SHALL NOT import `fleetent.platform.*` 或 `fleetent.im_gateway.*`（面命名空间）。违反时 CI 测试 SHALL 失败。

> 注：该规则与现有「`_COMPONENTS ✗→ fleetent.platform`」护栏在效果上部分重叠，本 requirement 补充明确的「核集合」定义并将 `im_gateway` 纳入面命名空间。

#### Scenario: 核模块不 import 控制面

- **WHEN** 护栏测试扫描核模块集合中任一文件的 import
- **THEN** 若其中出现对 `fleetent.platform.*` 的 import，测试 SHALL 失败

#### Scenario: 核模块不 import 边缘面

- **WHEN** 护栏测试扫描核模块集合中任一文件的 import
- **THEN** 若其中出现对 `fleetent.im_gateway.*` 的 import，测试 SHALL 失败

### Requirement: 面间互不直接依赖

四个面（①边缘 / ②控制 / ③编排 / ④摄取）SHALL NOT 互相直接 import。违反时 CI 测试 SHALL 失败。面的归属定义：

- **①边缘**：`fleetent.im_gateway.*`
- **②控制**：`fleetent.platform.{agent_management_console, connector_management, knowledge_base_management, model_provider_management, skill_management, user_management, chat_management, askit_console, reflection_management}.*`
- **③编排**：`fleetent.platform.agent_lifecycle.*`
- **④摄取**：`fleetent.knowledge_base.ingest.*`

#### Scenario: 控制面不直接依赖编排面

- **WHEN** 护栏测试扫描 ②控制 子包的 import
- **THEN** 若其中出现对 ③编排（`fleetent.platform.agent_lifecycle.*`）的直接 import，测试 SHALL 失败

#### Scenario: 编排面不直接依赖控制面

- **WHEN** 护栏测试扫描 ③编排 子包的 import
- **THEN** 若其中出现对 ②控制 子包的直接 import，测试 SHALL 失败

#### Scenario: 边缘面不直接依赖控制面

- **WHEN** 护栏测试扫描 ①边缘（`im_gateway.*`）的 import
- **THEN** 若其中出现对 ②控制 子包的直接 import，测试 SHALL 失败

### Requirement: reflection 两拆收口护栏

`reflection/` 引擎与 `platform/reflection_management/` 管理 API 之间的依赖方向 SHALL 受 CI 护栏强制。

#### Scenario: reflection 引擎不依赖管理 API

- **WHEN** 护栏测试扫描 `fleetent.reflection.*` 的 import
- **THEN** 若其中出现对 `fleetent.platform.reflection_management.*` 的 import，测试 SHALL 失败

#### Scenario: 管理 API 不直接 import 引擎私有 API

- **WHEN** 护栏测试扫描 `fleetent.platform.reflection_management.*` 的 import
- **THEN** 它 MAY import `fleetent.reflection.store`（产物读取）
- **AND** 它 SHALL NOT import `fleetent.reflection.reflection`（引擎私有模块）直接

### Requirement: audit_log 归基座

平台管理操作审计 SHALL 由顶层基座模块 `fleetent.audit_log` 提供，不由 `fleetent.governance.audit_log` 提供。

#### Scenario: audit_log 可经顶层基座路径导入

- **WHEN** 任意模块需要记录平台管理操作审计
- **THEN** 它 SHALL import `fleetent.audit_log`，而非 `fleetent.governance.audit_log`

#### Scenario: audit_log 不依赖业务逻辑

- **WHEN** 护栏测试扫描 `fleetent.audit_log` 的 import
- **THEN** 它 SHALL NOT import 任何业务能力模块（`runtime` / `memory` / `reflection` 等）或 `fleetent.platform.*`

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

