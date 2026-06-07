## ADDED Requirements

### Requirement: Vector store 作为独立基础设施组件

`vector_store` SHALL 作为顶层独立基础设施组件存在（`src/fleetent/vector_store/`），与 agent runtime 模块并列，而非置于 `intelligence/` 业务树下。它 SHALL 是无状态的共享底座，提供向量索引、检索、重排、命名空间管理能力，被 knowledge_base / memory / runtime 等多方消费。

#### Scenario: 作为顶层组件被消费
- **WHEN** knowledge_base 或 memory 需要向量索引/检索/重排
- **THEN** 它们 SHALL 通过 `vector_store` 的公共 API 使用
- **AND** vector_store SHALL 不感知具体调用方的业务语义

### Requirement: Vector store 依赖方向约束

`vector_store` MUST NOT import 任何业务能力模块（`knowledge_base`、`memory`、`reflection`、`long_term_ctx`），MUST NOT import `fleetent.platform`。它只被消费，不反向依赖业务或控制面。

#### Scenario: 不依赖业务模块
- **WHEN** 检查 `vector_store` 包的 import
- **THEN** 其中 SHALL NOT 出现对 knowledge_base / memory / reflection / long_term_ctx 的 import

#### Scenario: 不依赖 platform
- **WHEN** 检查 `vector_store` 包的 import
- **THEN** 其中 SHALL NOT 出现对 `fleetent.platform.*` 的 import

### Requirement: Vector store 公共 API 稳定

迁移为顶层组件 SHALL NOT 改变 `vector_store` 的公共 API 签名或语义。现有导出（search / upsert / delete / reindex / 各 namespace helper / rerank provider 等）行为保持不变。旧 import 路径 `fleetent.intelligence.vector_store` SHALL 通过 re-export shim 在迁移过渡期保持可用。

#### Scenario: 公共 API 行为不变
- **WHEN** 调用方经新路径 `fleetent.vector_store` 使用任一公共 API
- **THEN** 其行为 SHALL 与迁移前完全一致

#### Scenario: 旧路径过渡期可用
- **WHEN** 既有代码经旧路径 `fleetent.intelligence.vector_store` import
- **THEN** 在迁移过渡期 SHALL 仍然可用（re-export shim）
