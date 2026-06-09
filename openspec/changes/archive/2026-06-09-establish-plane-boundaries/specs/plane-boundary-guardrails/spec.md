## ADDED Requirements

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
