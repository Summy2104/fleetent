## ADDED Requirements

### Requirement: KnowledgeReadable / KnowledgeWritable Protocol 类型层约束

`knowledge_base.core` SHALL 暴露 `KnowledgeReadable` 与 `KnowledgeWritable` 两个 Protocol（`typing.Protocol`，structural subtyping）。`retrieval/` 中所有接受 store 实例的函数签名 SHALL 只接受 `KnowledgeReadable`，在类型层面不可见写方法（`upsert` / `delete` / `archive` 等）。`ingest/` 和 `management/` 接受 `KnowledgeWritable`。`core/KnowledgeStore` 同时满足两个 Protocol，无需显式继承。

#### Scenario: retrieval 函数类型签名只接受读接口

- **WHEN** mypy strict 检查 `knowledge_base.retrieval` 中函数对 store 参数的使用
- **THEN** 参数类型 SHALL 为 `KnowledgeReadable`
- **AND** 在该签名下 SHALL NOT 可见 `upsert` / `delete` / `archive` 等写方法

#### Scenario: 单一实现同时满足两个 Protocol

- **WHEN** mypy strict 检查 `core.KnowledgeStore`
- **THEN** `KnowledgeStore` SHALL 同时满足 `KnowledgeReadable` 与 `KnowledgeWritable`
- **AND** SHALL 只有一份 `KnowledgeStore` 实现（不拆子类）

#### Scenario: Protocol 不引入运行时开销

- **WHEN** `KnowledgeReadable` / `KnowledgeWritable` 被 import 使用
- **THEN** 它们 SHALL 使用 `typing.Protocol`（结构子类型），不使用 ABC 继承
- **AND** 现有 `KnowledgeStore` 无需修改继承关系即可满足
