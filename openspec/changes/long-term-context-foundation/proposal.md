## Why

fleetent 已经完成 SQLite semantic memory store、vector_store foundation 和 observability 基础能力，
但 agent-runtime 目前还没有统一的长期上下文注入入口。memory-layer 已经不再直接由 agent_loop
注入最近记忆；如果不补上 long-term-ctx，用户记忆即使被写入也不会参与后续回答。

同时，knowledge-base 仍处在迁移规划阶段，不应阻塞 long-term-ctx、reflection 和 platform
等模块继续推进。本 change 先把 knowledge-base 作为可选 provider 接入边界：当 KB 未实现、
未启用或返回空结果时，long-term-ctx 仍可正常基于 memory 工作。

## What Changes

- 新增 `long-term-ctx` 能力规范，定义长期上下文构建入口。
- 新增 `BuiltContext` 和 `ContextSource` public model。
- 新增 `build_context(user_id, query, agent_id, available_tokens)`：
  - `available_tokens <= 0` 时直接返回空上下文，不发起检索。
  - 调用 memory-layer semantic search。
  - 通过可选 knowledge provider 调用 knowledge-base search。
  - KB 未启用、未实现或无结果时正常降级，不影响 memory 注入。
  - 合并 memory 与 knowledge sources，按 token 预算截断。
- 新增 KB optional/null provider 约定：
  - 不实现 knowledge-base ingest、parser、connector、hybrid search 或 graph search。
  - 不要求 `openspec/specs/knowledge-base` 已具备运行时代码。
  - 后续 `knowledge-base-core` 只需实现相同 search provider contract。
- agent-runtime 通过 long-term-ctx 注入长期上下文，不再直接依赖 memory 或 knowledge-base。

## Capabilities

### New Capabilities

- `long-term-ctx`：长期上下文检索、合并、预算控制和注入文本构建。

### Modified Capabilities

- `agent-runtime`：在每次 agent run 开始前调用 long-term-ctx，而不是直接读取 memory。
- `observability`：后续可消费 `BuiltContext.sources` 记录 source attribution；本 change 只返回来源摘要，不新增 trace 事件。

## Dependencies

- 依赖 `memory-layer` semantic search 已完成。
- 依赖 `vector-store` foundation 已完成。
- 不依赖 `knowledge-base-core` 完成。

## Impact

- **代码**：
  - 新增 `fleetent.intelligence.long_term_ctx` 或等价模块位置。
  - 修改 agent-runtime 调用长期上下文入口。
  - 测试中 mock memory provider 与 knowledge provider。
- **数据**：
  - 不新增数据库表。
  - 不写入 knowledge-base 数据。
- **行为变化**：
  - 已保存的 semantic memory 可以重新参与 agent prompt。
  - KB 不可用时 agent 仍正常运行。
- **不包含**：
  - 不实现 knowledge-base core。
  - 不实现 graph_search。
  - 不实现 source attribution trace 写入。
  - 不实现 reflection。
  - 不实现 UI。
