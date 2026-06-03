# tool-arg-secret-redaction Specification

## Purpose
TBD - created by archiving change tool-arg-sanitization. Update Purpose after archive.
## Requirements
### Requirement: assistant tool_call 敏感名参数值在写入 trace 前被脱敏

trace 序列化层（`eval_logger`）在序列化 assistant 消息时，SHALL 解析其 `tool_calls[].function.arguments`（LLM 产出的原始 JSON），凡参数**名**命中敏感名判定的键，其值 MUST 在写入 trace 前被替换为占位符。脱敏 MUST 与既有 `_placeholder_images`（占位 base64 图片）位于同一序列化层、同一范式：只改将落盘的 trace 表示，不改写任何运行时工作对象。

#### Scenario: assistant tool_call 敏感名参数值在 trace 中被脱敏
- **WHEN** 一条 assistant 消息的 `tool_calls[].function.arguments` 中含一个名字命中敏感名判定的键（如 `api_key`、`password`）
- **THEN** 写入 trace 的该 tool_call 参数值被替换为占位符，原值不以明文落盘

#### Scenario: 非敏感名参数值在 trace 中保持原样
- **WHEN** tool_call 参数名未命中敏感名判定（如 `query`、`path`）
- **THEN** 写入 trace 的该参数值保持原样，不被替换为占位符

#### Scenario: 无 tool_calls 的消息按既有方式序列化
- **WHEN** 一条消息不含 `tool_calls`（如普通 user / assistant 文本消息或含图片块的消息）
- **THEN** 序列化行为与既有 `_serialize` / `_placeholder_images` 一致，不受 tool_call 脱敏逻辑影响

### Requirement: 脱敏复用 SB5 敏感名规则，单一事实来源

trace 层 tool_call 参数脱敏的敏感名判定 MUST 复用 `sandbox_secrets.is_sensitive_name`（同一套规则与同一可注入的 `SENSITIVE_TOKENS` 常量），不得在 `eval_logger` 侧另立一份敏感名规则。扩展或调整 `sandbox_secrets` 的敏感名常量时，trace 脱敏与沙箱 env 过滤 MUST 同步生效。

#### Scenario: 复用 SB5 同一敏感名规则
- **WHEN** 敏感名常量经 monkeypatch 在 `sandbox_secrets` 处被扩展或调整
- **THEN** trace 层 tool_call 参数脱敏的命中判定随之变化，与沙箱 env 过滤共用同一套规则

### Requirement: 脱敏仅作用于 trace，session 工作上下文不脱敏

脱敏 SHALL 仅作用于 trace 落盘表示（trace only）。session JSON 持久化的消息 MUST NOT 被脱敏：session 是 LLM 每轮要回读的工作上下文，脱敏会丢失上下文、破坏对话连续性；对话内出现的密钥属于对话本身。传给工具函数的运行时参数同样 MUST NOT 受影响。

#### Scenario: session 工作上下文保留原始参数值
- **WHEN** 一条含敏感名 tool_call 参数的 assistant 消息被持久化到 session
- **THEN** session 中该参数值保持原始明文，供 LLM 下一轮回读，不被脱敏

#### Scenario: 脱敏不污染运行时对象
- **WHEN** trace 序列化对某条消息的 tool_call 参数做脱敏
- **THEN** 传入序列化层的原始消息对象不被改写，运行时工作上下文与传给工具的参数均为原值

### Requirement: 仅名过滤的局限被显式承认

trace 层 tool_call 参数脱敏 SHALL 仅依据参数**名**判定，MUST NOT 扫描参数**值**的文本内容以发现内嵌密钥。该局限与 SB5（`sandbox_secrets`）一致，值内嵌的密钥不在本能力的脱敏覆盖范围内。

#### Scenario: 值内嵌密钥不被脱敏（已知局限）
- **WHEN** 一个非敏感名参数（如 `note`）的值文本里内嵌了一段密钥
- **THEN** 该值不被脱敏（仅名过滤的已知局限，与 SB5 一致），写入 trace 时不做值内容扫描
