## ADDED Requirements

### Requirement: 并发检索

`build_context()` SHALL 并发执行 memory、knowledge、agent_memory 三路检索（而非顺序等待），整体检索延迟不超过最慢一路。各路返回结果后的合并、排序与预算控制语义不变。

#### Scenario: 三路并发而非顺序

- **WHEN** `build_context()` 触发三路检索，其中每路检索人为延迟 D
- **THEN** 三路检索的总耗时约为 D（最慢一路），而非约 3×D（顺序之和）

#### Scenario: 单路结果不依赖其他路完成

- **WHEN** 某一路检索快速返回、另一路较慢
- **THEN** 快路结果不被慢路阻塞，最终合并结果包含所有已成功返回路的结果

### Requirement: 单路检索超时降级

每路检索 SHALL 受单路超时约束（由配置 `retrieval_timeout_seconds` 控制，默认 5 秒）。某路超时 SHALL 降级为该路空结果、记一条 `warning` 级日志，并 MUST NOT 阻塞其余路或使 `build_context()` 抛出异常。超时路在后续合并中等价于该路返回空。

#### Scenario: 单路超时降级为空结果

- **WHEN** memory 检索耗时超过 `retrieval_timeout_seconds`
- **THEN** memory 路被视为空结果，knowledge 与 agent_memory 路正常并入上下文，`build_context()` 正常返回，不抛异常

#### Scenario: 超时记录可观测日志

- **WHEN** 某路检索超时被降级
- **THEN** 系统记录一条 `warning` 日志，标明超时的检索路名称

#### Scenario: 全部超时返回空上下文

- **WHEN** 三路检索均超时
- **THEN** `build_context()` 返回空 `BuiltContext`（`text` 为空、`sources` 为空），与"三路均无结果"行为一致

### Requirement: 检索分段计时可观测

`build_context()` SHALL 为每路检索记录耗时与是否超时，使"哪一路慢"可从结构化日志/trace 直接判定，无需复现。

#### Scenario: 每路记录耗时

- **WHEN** `build_context()` 完成一次检索
- **THEN** memory、knowledge、agent_memory 三路各自的耗时（毫秒/秒）与超时标志被记录到结构化日志或 trace
