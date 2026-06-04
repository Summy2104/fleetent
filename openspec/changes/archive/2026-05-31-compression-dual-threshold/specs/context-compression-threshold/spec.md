## ADDED Requirements

### Requirement: 双阈值触发压缩

上下文压缩 SHALL 使用两个相对 `max_tokens` 的阈值：`Tmax`（触发压缩的上限比例）与 `Tretained`（压缩目标比例）。当估算 token 超过 `max_tokens * Tmax` 时，压缩 MUST 被触发；当估算 token 未超过 `max_tokens * Tmax` 时，自动检查 MUST NOT 触发压缩，消息原样返回。

#### Scenario: 超过 Tmax 触发压缩
- **WHEN** 自动检查时估算 token 超过 `max_tokens * Tmax`
- **THEN** 触发压缩，返回的消息序列被压缩（含摘要前缀 + 保留尾部）

#### Scenario: 未超过 Tmax 不压缩
- **WHEN** 自动检查时估算 token 未超过 `max_tokens * Tmax`
- **THEN** 不触发压缩，消息原样返回

### Requirement: 压缩回落到 Tretained 目标线

压缩 SHALL 以 `max_tokens * Tretained` 为目标线：压缩后的估算 token MUST 回落到目标线附近或以下，但在保持工具调用对（tool_call / tool_result）完整的前提下，实际值 MAY 略高于目标线。压缩 MUST NOT 为命中目标线而在 tool_call 与其结果之间截断消息。

#### Scenario: 压缩后回落到目标线附近
- **WHEN** 因超过 `Tmax` 触发压缩
- **THEN** 压缩后的估算 token 回落到 `max_tokens * Tretained` 附近或以下

#### Scenario: 目标线让位于工具对完整性
- **WHEN** 严格回落到目标线会切断某个 tool_call 与其对应结果
- **THEN** 保留完整的工具调用对，压缩后估算 token 允许略高于目标线，消息序列对 LLM 合法

### Requirement: 两阈值保持间距

配置 MUST 满足 `Tretained < Tmax`。两阈值之间 SHALL 保持足够间距，使压缩到 `Tretained` 后不会因少量新增消息立即再次越过 `Tmax`，从而避免频繁压缩与 prompt 缓存反复失效。

#### Scenario: 默认配置间距有效抑制即时再触发
- **WHEN** 使用默认阈值，一次压缩使估算 token 回落到 `Tretained` 目标线
- **THEN** 压缩后的估算 token 低于 `Tmax` 触发线，下一轮少量新增消息不会立即再次触发压缩

#### Scenario: 拒绝非法阈值配置
- **WHEN** 注入的配置不满足 `Tretained < Tmax`
- **THEN** 该配置被判为非法（报错或被规整），不会以 `Tretained >= Tmax` 的形式生效

### Requirement: 手动触发压缩

压缩框架 SHALL 提供手动触发入口（`/compact` 命令语义）：当调用方请求强制压缩时，无论当前估算 token 是否超过 `Tmax`，MUST 立即执行压缩并回落到 `Tretained` 目标线。

#### Scenario: 未超阈值时手动强制压缩
- **WHEN** 当前估算 token 未超过 `Tmax`，调用方请求手动强制压缩
- **THEN** 仍执行压缩，压缩后估算 token 回落到 `Tretained` 目标线附近或以下

### Requirement: 上下文过长错误触发压缩

压缩框架 SHALL 提供供「LLM 报上下文过长错误」时使用的压缩入口：当调用方因 LLM 返回上下文过长类错误而请求压缩时，MUST 执行压缩并回落到 `Tretained` 目标线，供调用方据此重试。

#### Scenario: 上下文过长错误后压缩供重试
- **WHEN** 调用方因 LLM 返回上下文过长类错误而请求压缩
- **THEN** 执行压缩并回落到 `Tretained` 目标线，返回压缩后的消息序列供调用方重试

### Requirement: 阈值可配置与注入

`Tmax` 与 `Tretained` MUST 支持部署级配置（`Settings` 的 env 字段）并支持通过注入的配置覆盖默认值。压缩逻辑 MUST NOT 依赖全局可变状态，阈值 MUST 可在测试中通过传入配置注入而无需实例化真实 `Settings`。

#### Scenario: 配置注入覆盖默认阈值
- **WHEN** 调用压缩时传入自定义的 `Tmax` / `Tretained` 配置
- **THEN** 压缩按注入的阈值判定触发与目标线，而非默认值
