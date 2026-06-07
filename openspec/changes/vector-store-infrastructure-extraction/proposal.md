## Why

`vector_store`（embedding / rerank / backend / namespaces / reindex）是**无状态的共享基础设施**，被 `knowledge_base`、`memory`（5 处）、`runtime/agent_app`、`agent_config` 共 9 处消费。但它现在物理上躺在 `intelligence/vector_store/`——一个被 CLAUDE.md 标为"agent runtime 业务"的目录树下，定位错位（基础设施被当成 agent 业务模块）。

这是 [intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) 的**阶段1**：先把底座稳住，因为后续 KB 重构（阶段2）依赖它。它是整条路线里把握最大、最独立的一步——纯物理移动 + 兼容 shim，不改任何行为或 API。

## What Changes

- **物理迁移**：`src/fleetent/intelligence/vector_store/` → `src/fleetent/vector_store/`，作为与 runtime/session/governance 并列的顶层基础设施组件。
- **兼容 shim**：旧路径 `intelligence/vector_store/__init__.py` 保留为 re-export shim，9 处调用方分批迁移，迁移完成前不删 shim。
- **依赖契约固化**：vector_store 不 import 任何业务模块（KB/memory）、不 import platform；它只被消费，不反向依赖。
- **行为零变更**：公共 API（`search`/`upsert`/`reindex`/`delete`/各 namespace helper/rerank provider 等 15 个导出）签名与语义完全不变。

## Capabilities

### New Capabilities
- `vector-store`: 把 vector_store 作为独立基础设施组件的边界契约固化为 spec（公共 API 面 + 依赖方向规则）。此前它只有实现、无 spec。

### Modified Capabilities
<!-- 无行为变更 -->

## Impact

- **物理移动**：`intelligence/vector_store/` → `vector_store/`（backend/embeddings/namespaces/reindex/rerank/runtime 6 文件整体移动）。
- **调用方**（9 处 import 路径更新，或暂走 shim）：`knowledge_base/{config,runtime}`、`memory/{extraction,maintenance,operations,search,shared}`、`runtime/agent_app`、`agent_config`。
- **shim**：`intelligence/vector_store/__init__.py` re-export 顶层 `vector_store`，保留至所有调用方迁移完成（沿用 roadmap Shim 策略）。
- **CLAUDE.md**：架构目录树中 vector_store 的位置更新留到阶段5 统一改（本 change 先动代码 + shim，契约文字阶段5 收口）。
- **不含**：vector_store 内部重构、rerank/embedding 逻辑变更、namespace 约定变更。
