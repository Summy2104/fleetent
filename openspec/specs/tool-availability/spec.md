# tool-availability Specification

## Purpose
工具可用性声明机制，允许工具在运行时按条件决定是否暴露给 LLM，`get_schemas()` 每次调用实时评估，注册表本身不受影响。

## Requirements

### Requirement: @tool 装饰器支持 availability 可用性声明
`@tool` 装饰器 SHALL 接受可选 `availability` 参数（类型 `Callable[[], bool] | None`，默认 `None`）；`None` 表示始终可用（与现有行为兼容）；非 `None` 时为运行时可用性检查函数，`True` 表示当前可用，`False` 表示不可用。availability 函数 SHALL 为纯同步函数，执行时间应在毫秒级（不得做 I/O 或网络调用）。

#### Scenario: 无 availability 声明的工具始终包含在 schema 中
- **WHEN** 工具使用 `@tool` 不带 `availability` 参数注册
- **THEN** `get_schemas()` 始终包含该工具（与现有行为一致）

#### Scenario: 声明 availability=None 等同于始终可用
- **WHEN** 工具使用 `@tool(availability=None)` 注册
- **THEN** `get_schemas()` 始终包含该工具

### Requirement: get_schemas() 过滤当前不可用的工具
`get_schemas()` SHALL 在每次调用时评估每个工具的 availability 函数（若已声明）；availability 返回 `False` 的工具 SHALL 不出现在返回的 schema 列表中；availability 返回 `True` 或未声明的工具正常包含。过滤结果不被缓存（每次调用均实时评估）。

#### Scenario: 不可用工具被过滤出 schema
- **WHEN** 工具声明 `availability=lambda: False`（或运行时条件不满足）
- **THEN** `get_schemas()` 返回列表中不包含该工具

#### Scenario: 条件变化后工具重新出现
- **WHEN** 工具声明 `availability=lambda: bool(os.getenv("SEARXNG_URL"))`，且该环境变量从未设置变为已设置
- **THEN** 下一次 `get_schemas()` 调用中该工具重新出现

#### Scenario: availability 抛出异常时工具被视为不可用
- **WHEN** availability 函数执行时抛出异常
- **THEN** 该工具被视为不可用（不包含在 schema 中），异常被捕获并记录 warning 日志，不传播

### Requirement: 工具注册表保留不可用工具（视图而非删除）
availability 机制 SHALL 是视图层过滤，不影响 `_registry` 中的实际注册；不可用工具仍留在 `_registry` 中，一旦 availability 条件恢复，无需重新注册即可再次出现在 schema 中。

#### Scenario: 不可用工具仍在注册表中
- **WHEN** 工具 availability 返回 False
- **THEN** `dispatch(name)` 仍可调用该工具（注册表未删除），只是 LLM 看不到它

#### Scenario: 条件恢复后无需重启即可使用
- **WHEN** 进程运行中 `SEARXNG_URL` 被动态设置
- **THEN** 下一次 `get_schemas()` 即包含 `web_search`，无需重启服务
