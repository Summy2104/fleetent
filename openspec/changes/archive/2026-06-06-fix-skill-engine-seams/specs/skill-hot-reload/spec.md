## MODIFIED Requirements

### Requirement: 重扫期间原子切换，无半空索引窗口

重扫 SHALL 先把结果构建到一个新的索引对象，全部构建成功后再整体替换当前索引引用（原子切换）。在重扫进行中，任一读取索引的操作 MUST 要么看到完整的旧索引、要么看到完整的新索引，绝不会观察到部分填充的中间态。

管理 API 的 `engine_reload()` seam SHALL 调用 `skill_registry.reload()`（原子替换），不得调用 `skill_registry.scan()`（破坏性 clear+update 操作会在 clear 与 update 之间暴露空索引）。

#### Scenario: 重扫不暴露半空索引

- **WHEN** 重扫正在构建新索引的过程中有请求读取索引
- **THEN** 该请求看到的是完整的旧索引（构建尚未完成），而非被清空或部分填充的索引

#### Scenario: 构建完成后整体切换

- **WHEN** 新索引构建全部成功
- **THEN** 当前索引被整体替换为新索引，此后读取看到完整的新索引

#### Scenario: engine_reload 调用原子 reload

- **WHEN** 管理 API `POST /admin/skills/reload` 被调用
- **THEN** `engine_reload()` 调用 `skill_registry.reload()`，不调用 `skill_registry.scan()`
- **AND** 并发请求在重扫期间看到完整旧索引，重扫完成后看到完整新索引
