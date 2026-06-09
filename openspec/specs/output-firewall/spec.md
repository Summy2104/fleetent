# output-firewall Specification

## Purpose
TBD - created by archiving change output-firewall. Update Purpose after archive.
## Requirements
### Requirement: 所有工具结果进入上下文前统一脱敏

任何工具的执行结果在进入 `messages`（即模型上下文与持久化 session）之前 SHALL 经 `redact_secrets` 脱敏，而不只是 `run_code` 的输出。覆盖 `run()` 与 `run_stream()` 两条路径。

#### Scenario: 文件工具读到的密钥被脱敏
- **WHEN** read_file/search_content 等工具返回含密钥（如 vendor API key、Authorization 头、密钥名赋值）的内容
- **THEN** 进入 messages 的该工具结果中的密钥被替换为 `[REDACTED]`

#### Scenario: 不含密钥的结果不变
- **WHEN** 工具结果不含可识别密钥
- **THEN** 内容原样进入 messages，不被改写

### Requirement: 脱敏在结果截断之前执行

输出防火墙 SHALL 在工具结果被截断（`truncate_tool_result`）之前脱敏，使跨截断边界的密钥也能被掩码。

#### Scenario: 跨边界密钥被掩码
- **WHEN** 一个密钥恰好横跨工具结果的截断边界
- **THEN** 它在截断前已被脱敏，不会有残片进入上下文

### Requirement: placeholder 占位结果豁免脱敏

系统自产的 placeholder 结果（审批拒绝 / 策略 deny / Action Gate reject 的占位消息）SHALL NOT 被脱敏改写——它们不含外部密钥。

#### Scenario: 拒绝占位不被改
- **WHEN** 一次工具调用被 Action Gate reject，产生拒绝占位文本
- **THEN** 该占位文本原样进入 messages，不经脱敏替换

