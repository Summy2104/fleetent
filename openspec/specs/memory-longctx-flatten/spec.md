# memory-longctx-flatten Specification

## Purpose
固化 memory 作为顶层 agent 能力组件、long_term_ctx 作为独立顶层聚合包（含 _policy）的边界契约：shared-memory 能力本体留 agent 侧而审计为 platform 薄壳，并以护栏约束 memory/long_term_ctx 的依赖方向。

## Requirements
### Requirement: Memory 作为顶层 agent 能力组件

`memory`（记忆提取/检索/自维护/shared 核心/trends）SHALL 作为顶层组件存在（`src/fleetent/memory/`），与 runtime/session 并列，而非置于 `intelligence/` 业务树下。其 `store` SHALL 作为域内 core。memory 的写 SHALL 全部由 agent 对话/自维护自然产生，无外部摄取写边界，故 store SHALL 保持单一接口、不强制 Readable/Writable 拆分。

#### Scenario: memory 顶层可消费
- **WHEN** runtime 或 long_term_ctx 需要记忆提取/检索
- **THEN** 它们 SHALL 经顶层 `fleetent.memory` 使用
- **AND** memory store SHALL 以单一接口提供读写

### Requirement: Long-term context 作为独立顶层聚合包

`long_term_ctx` SHALL 作为独立顶层包存在（`src/fleetent/long_term_ctx/`，含 `_policy`），由 `runtime` 在对话内调用，聚合 `memory` 与 `knowledge_base.retrieval` 注入上下文。它 SHALL NOT 并入 `runtime`；其"更高层"由依赖方向（依赖能力域、被 runtime 调、不被能力域反依赖）表达。

#### Scenario: long_term_ctx 独立于 runtime
- **WHEN** 检查源码树
- **THEN** `long_term_ctx` SHALL 是独立顶层包，而非 `runtime` 的子模块
- **AND** `runtime` SHALL 依赖 `long_term_ctx`，`long_term_ctx` SHALL NOT 依赖 `runtime`

### Requirement: Shared-memory 控制面薄壳归 platform

shared-memory 的能力本体（创建/更新/归档/检索/被注入、`apply_shared_memory_proposal`）SHALL 留在 agent 侧 `memory.shared`。其人工录入的**审计记录**（`record_shared_memory_admin_audit`）SHALL 作为 platform 薄壳，能力本体 SHALL NOT 因审批/审计而移走（判据二）。

#### Scenario: 能力本体留 agent
- **WHEN** agent 在无 platform 环境检索/注入 shared-memory
- **THEN** 检索与被注入 SHALL 正常工作，不依赖 platform

#### Scenario: 审计是 platform 薄暴露面
- **WHEN** 人工录入 shared-memory 并需记录治理审计
- **THEN** 审计记录 SHALL 经 platform 薄壳完成
- **AND** agent 侧能力本体 SHALL NOT 因此依赖 platform

### Requirement: Memory / long_term_ctx 依赖方向护栏

系统 SHALL 以 CI 强制的测试护栏断言：`memory` MUST NOT import `long_term_ctx`（能力域不反依赖聚合者）；`memory` / `long_term_ctx` MUST NOT import `fleetent.platform.*`；`memory` MUST NOT import `reflection`（阶段3 审批门居中破环后由护栏强制）。

#### Scenario: 能力域不反依赖聚合者
- **WHEN** 护栏测试检查 `memory` 的 import
- **THEN** 若其中出现对 `long_term_ctx` 的 import，测试 SHALL 失败

#### Scenario: 组件不依赖控制面
- **WHEN** 护栏测试检查 `memory` / `long_term_ctx` 的 import
- **THEN** 若其中出现对 `fleetent.platform.*` 的 import，测试 SHALL 失败

### Requirement: 公共 API 行为稳定

顶层化 SHALL NOT 改变 memory / long_term_ctx 的公共 API 行为与语义。调用方经顶层路径 `fleetent.memory` / `fleetent.long_term_ctx` 使用任一公共 API 的行为 SHALL 与迁移前完全一致。

#### Scenario: 行为不变
- **WHEN** 调用方经新路径使用 memory / long_term_ctx 公共 API
- **THEN** 其行为 SHALL 与迁移前完全一致
