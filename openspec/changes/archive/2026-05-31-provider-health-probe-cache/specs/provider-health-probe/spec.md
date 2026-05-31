## ADDED Requirements

### Requirement: provider 健康状态缓存

系统 SHALL 维护每个 provider（按 model 标识）的连续失败计数与不可用截止时间。该缓存 MUST 为可注入实例，不得使用模块级裸全局可变状态，以保证测试可隔离。

#### Scenario: 初始状态可用
- **WHEN** 查询一个从未记录过失败的 provider 是否可用
- **THEN** 返回可用，连续失败计数为零

#### Scenario: 缓存可注入隔离
- **WHEN** 测试通过注入替换健康缓存实例并设置假时钟
- **THEN** 该测试对缓存的读写不影响其它测试，无需真实 sleep

### Requirement: 连续失败达阈值标记不可用

当某 provider 的连续失败次数达到配置阈值时，缓存 MUST 将其标记为暂时不可用，持续配置的冷却时间。冷却期内查询该 provider 可用性 MUST 返回不可用。该阈值与冷却时间 MUST 可通过构造参数或配置覆盖默认值。

#### Scenario: 达到失败阈值后进入冷却
- **WHEN** 某 provider 连续失败次数达到配置阈值
- **THEN** 在冷却时间内查询该 provider 返回不可用

#### Scenario: 未达阈值仍可用
- **WHEN** 某 provider 失败次数尚未达到阈值
- **THEN** 查询该 provider 仍返回可用

### Requirement: fallback 遍历跳过不可用 provider

`_call_with_fallback` 与 `_stream_with_fallback` 在遍历候选模型时 MUST 跳过当前处于冷却期（不可用）的 provider，避免每次都对其发起调用并等待超时。当所有候选都被跳过或失败时，系统 MUST 不静默返回空结果，而是按既有契约抛出异常交由上层处理。

#### Scenario: 冷却期内的 provider 被跳过
- **WHEN** 候选模型列表中首选 provider 处于冷却期、后续 provider 可用
- **THEN** fallback 遍历不对首选 provider 发起调用，直接尝试可用的后续 provider

#### Scenario: 全部候选不可用时不静默失败
- **WHEN** 所有候选 provider 均处于冷却期或调用失败
- **THEN** 系统抛出异常交由 agent_loop 上层处理，不返回空结果

### Requirement: 冷却期满半开重试

冷却时间到期后，缓存 MUST 允许该 provider 重新进入候选（半开探测），即冷却到点后 `is_available` 返回可用。半开放行后的一次调用成功 MUST 恢复该 provider 并清零失败计数；失败 MUST 重新累计，达阈值则重新进入冷却。

#### Scenario: 冷却到点后允许重试
- **WHEN** 某 provider 的冷却时间已过
- **THEN** 查询该 provider 返回可用，fallback 遍历会再次尝试它

#### Scenario: 半开重试失败重入冷却
- **WHEN** 冷却到点后半开重试再次失败并达到阈值
- **THEN** 该 provider 重新被标记为不可用并进入新一轮冷却

### Requirement: 成功调用立即恢复

任一对 provider 的成功调用 MUST 立即将其连续失败计数重置为零并清除不可用标记，使其后续查询返回可用。

#### Scenario: 成功调用清零失败计数
- **WHEN** 某 provider 在若干次失败后出现一次成功调用
- **THEN** 其连续失败计数归零，立即恢复为可用状态

### Requirement: 失败判定范围

缓存的失败 MUST 仅由「应切换 provider」的错误触发——即错误分类层判定 `should_switch_model` 为真者（限流 429 / 服务不可用 503）。其它错误（4xx 鉴权/参数错误等 `should_switch_model` 为假者）MUST 不计为失败，也不标记 provider 不可用，仍按现状直接向上抛出。

#### Scenario: 应切换的限流/服务不可用错误计为失败
- **WHEN** provider 返回分类为应切换的错误（429 或 503）
- **THEN** 该 provider 的连续失败计数增加

#### Scenario: 鉴权/参数错误不计为失败
- **WHEN** provider 返回 401 或 400 等 `should_switch_model` 为假的错误
- **THEN** 该 provider 的失败计数不变，错误直接向上抛出
