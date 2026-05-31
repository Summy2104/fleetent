## Why

fleetent 已经具备 SQLite agent traces、usage summary 和 semantic memory 基础能力，但 reflection
仍只停留在远期设想。完整 reflection 涉及 memory 自动维护、skill 自动生成和 knowledge-base
质量分析，范围过大，也容易在 MVP 阶段引入危险的自动写回。

本 change 先建立 reflection 的最小地基：从 traces 和 memory 中读取信号，生成结构化建议报告，
但不自动改变 memory、skills 或 knowledge-base。这样可以先验证 reflection 的输入、输出和报告质量，
再逐步扩展到半自动或自动维护。

## What Changes

- 新增 `reflection` 能力规范，定义只读分析与 report 输出。
- 新增 `ReflectionReport` 和 `ReflectionFinding` public model。
- 新增 `run_reflection(scope)` public API：
  - 通过 `observability.query_trace_events()` 读取 agent run history。
  - 读取 memory-layer 可用的语义记忆信号。
  - 返回或保存结构化 report。
- 第一阶段 report 类型：
  - `memory_candidate`：对话中反复出现、可能应写入 memory 的事实。
  - `memory_conflict`：已有 memory 或 trace 信号中可能冲突的事实。
  - `skill_opportunity`：重复任务模式，未来可能沉淀为 skill。
- 明确不做自动写回：
  - 不创建、更新或删除 `memory_items`。
  - 不创建、更新或删除 `skills/` 文件。
  - 不分析 knowledge-base，也不写 `kb_reflection_reports`。

## Capabilities

### New Capabilities

- `reflection`：从 traces 与 memory 信号中生成结构化改进建议。

### Modified Capabilities

- `observability`：作为 reflection 第一阶段主要输入，reflection 只通过 public trace query API 读取。
- `memory-layer`：作为 reflection 第一阶段输入，reflection 不直接改写 memory。

## Dependencies

- 依赖 `observability-sqlite-agent-traces` 已完成。
- 依赖 `memory-sqlite-semantic-store` 已完成。
- 不依赖 `knowledge-base-core`。
- 不依赖 `long-term-context-foundation` 完成。

## Impact

- **代码**：
  - 新增 `fleetent.intelligence.reflection` 或等价模块位置。
  - 新增只读 report 生成 API。
  - 测试中 mock observability 与 memory-layer。
- **数据**：
  - 可新增 reflection-owned `reflection_reports` 表保存报告。
  - 不修改 `memory_items`、`traces` 或 `skills/`。
- **行为变化**：
  - 系统可以生成 reflection 建议，但不会自动应用建议。
- **不包含**：
  - 不做 memory 自动清理、合并或写回。
  - 不做 skill proposal 表、permission_gate 审批或文件写入。
  - 不做 knowledge-base reflection。
  - 不做 UI。
