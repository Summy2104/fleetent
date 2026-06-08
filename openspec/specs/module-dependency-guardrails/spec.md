# module-dependency-guardrails Specification

## Purpose
以 CI 强制的测试护栏锁定 intelligence 重构后的模块依赖方向（纲领 §6），并固化 intelligence 聚合层的移除，防止禁止边的反向 import 回潮。

## Requirements
### Requirement: 组件依赖方向护栏

系统 SHALL 以 CI 强制的测试护栏，断言 intelligence 重构后的依赖方向规则（纲领 §6）。违反任一禁止边的 import SHALL 导致测试失败。

禁止边至少包括：
- `knowledge_base.retrieval` MUST NOT import `knowledge_base.ingest`
- `memory` / `knowledge_base` MUST NOT import `long_term_ctx` / `reflection`
- `vector_store` / `knowledge_base` / `memory` / `reflection` / `long_term_ctx`（组件）MUST NOT import `fleetent.platform.*`
- `vector_store` MUST NOT import 任何业务能力模块

#### Scenario: 读边界不依赖写边界
- **WHEN** 护栏测试检查 `knowledge_base.retrieval` 的 import
- **THEN** 若其中出现对 `knowledge_base.ingest` 的 import，测试 SHALL 失败

#### Scenario: 能力域不反依赖聚合者
- **WHEN** 护栏测试检查 `memory` / `knowledge_base` 的 import
- **THEN** 若其中出现对 `long_term_ctx` / `reflection` 的 import，测试 SHALL 失败

#### Scenario: 组件不依赖控制面
- **WHEN** 护栏测试检查任一组件包的 import
- **THEN** 若其中出现对 `fleetent.platform.*` 的 import，测试 SHALL 失败

### Requirement: intelligence 聚合层移除

重构收口后，`src/fleetent/intelligence/` 目录及其 re-export shim SHALL 被删除；原 intelligence 内容 SHALL 以顶层组件形式存在。CLAUDE.md 架构契约 SHALL 与之一致（移除 intelligence 节点、平铺组件、记录依赖规则与三条判据）。

#### Scenario: intelligence 目录不再存在
- **WHEN** 收口完成后检查源码树
- **THEN** `src/fleetent/intelligence/` SHALL 不存在
- **AND** 原内容 SHALL 可经顶层路径（vector_store / knowledge_base / memory / reflection / long_term_ctx）导入

#### Scenario: 无残留旧路径 import
- **WHEN** 全仓检查 import
- **THEN** SHALL NOT 存在对 `fleetent.intelligence.*` 的 import（shim 已删）
