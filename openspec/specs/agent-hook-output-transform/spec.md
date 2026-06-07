### Requirement: output_transform 最终回复变换与观测

当 hooks 启用且注册了 `output_transform` hook 时，agent loop SHALL 在最终 reply 定稿后、返回给调用方前（`run` 的两处 `return reply` 及 `run_stream` 的两处 `yield done`）`dispatch("output_transform", ctx{content: reply})`，并将 `modified_content` 替换最终回复。未启用或无注册时 MUST 零行为变化。

#### Scenario: hook 改写最终回复
- **WHEN** `output_transform` hook 返回 `modified_content`
- **THEN** 调用方（IM 网关/HTTP 客户端）收到改写后的 reply（脱敏/格式化/重写）

#### Scenario: hook 仅做副作用观测
- **WHEN** `output_transform` hook 返回 `None`
- **THEN** 回复原样返回，流程无变化

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `output_transform` 注册
- **THEN** 最终回复与未引入本能力时完全一致
