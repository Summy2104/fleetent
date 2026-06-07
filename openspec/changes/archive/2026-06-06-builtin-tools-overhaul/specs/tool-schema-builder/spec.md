## ADDED Requirements

### Requirement: schema builder 支持 list 类型参数
`_build_schema()` SHALL 将 `list[T]`（T 为任意基础类型）注解转换为 JSON Schema `{"type": "array", "items": {"type": "<T>"}}` 格式；支持 `list[str]`、`list[int]`、`list[float]`、`list[bool]`。

#### Scenario: list[str] 参数生成正确 schema
- **WHEN** 工具函数声明参数 `items: list[str]`
- **THEN** 生成的 schema 中该参数为 `{"type": "array", "items": {"type": "string"}}`，且在 `required` 列表中

#### Scenario: list[int] 参数生成正确 schema
- **WHEN** 工具函数声明参数 `counts: list[int]`
- **THEN** 生成的 schema 中该参数为 `{"type": "array", "items": {"type": "integer"}}`

### Requirement: schema builder 支持 Optional 参数（非必填）
`_build_schema()` SHALL 将 `Optional[T]`（等价于 `T | None`）注解识别为非必填参数（不进入 `required` 列表），类型取 T 对应的 JSON Schema 类型。

#### Scenario: Optional[str] 参数不在 required 中
- **WHEN** 工具函数声明参数 `note: Optional[str] = None`
- **THEN** 生成的 schema 中 `note` 类型为 `"string"`，且不出现在 `required` 列表中

#### Scenario: 带默认值参数不在 required 中
- **WHEN** 工具函数声明参数 `limit: int = 200`
- **THEN** `limit` 不出现在 `required` 列表，类型为 `"integer"`

### Requirement: schema builder 支持 Literal 枚举约束
`_build_schema()` SHALL 将 `Literal["a", "b", "c"]` 注解转换为 `{"type": "string", "enum": ["a", "b", "c"]}`；Literal 值全为字符串时 type 为 `"string"`，全为整数时 type 为 `"integer"`。

#### Scenario: Literal[str] 生成 enum schema
- **WHEN** 工具函数声明参数 `action: Literal["set", "get", "clear"]`
- **THEN** 生成的 schema 为 `{"type": "string", "enum": ["set", "get", "clear"]}`

### Requirement: schema builder 支持 Annotated 参数级描述
`_build_schema()` SHALL 将 `Annotated[T, "描述文字"]` 注解提取元数据中的第一个字符串作为该参数的 `description` 字段，写入 JSON Schema properties。

#### Scenario: Annotated 参数生成带 description 的 schema
- **WHEN** 工具函数声明参数 `command: Annotated[str, "要执行的 Shell 命令"]`
- **THEN** 生成的 schema 中该参数含 `"description": "要执行的 Shell 命令"`

#### Scenario: 无 Annotated 的参数无 description 字段
- **WHEN** 工具函数声明参数 `path: str`（无 Annotated）
- **THEN** 生成的 schema 中该参数无 `description` 字段

### Requirement: schema builder 保持与现有 out-of-band 参数过滤的兼容
`_build_schema()` 升级后 SHALL 继续过滤所有 `_OUT_OF_BAND_PARAMS`（`cancel_token`、`tool_context`、`client`），无论其类型注解为何，这些参数均不出现在 LLM-facing schema 中。

#### Scenario: cancel_token 参数不进入 schema
- **WHEN** 工具函数声明 `cancel_token: CancelToken | None = None`
- **THEN** schema 中不包含 `cancel_token` 参数
