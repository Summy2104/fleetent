## ADDED Requirements

### Requirement: run() 通过 usage_out 出参透出 token usage

`agent_loop.run()` SHALL 接受可选参数 `usage_out: list | None = None`。当 run 正常完成且取得 token usage 时，若 `usage_out` 非 None，MUST append 一个 `(prompt_tokens, completion_tokens)` 元组。run() 的返回类型 MUST 保持为 str 不变（不破坏现有调用方）。run 提前返回（未跑 LLM，无 usage）时 MUST NOT append。

#### Scenario: 正常完成时填充 usage_out
- **WHEN** 调用 `run(messages, usage_out=[])` 且 run 正常完成并取得 usage
- **THEN** `usage_out` 含一个 `(prompt_tokens, completion_tokens)` 元组

#### Scenario: 不传 usage_out 时行为不变
- **WHEN** 调用 `run(messages)` 不传 usage_out
- **THEN** run 行为与改动前完全一致，返回 str

#### Scenario: 无 usage 时不填充
- **WHEN** run 提前返回（未产生 usage）且传入 usage_out=[]
- **THEN** usage_out 保持为空

### Requirement: normalizer 将 token usage 传给 save

IM 消息处理路径（normalizer）SHALL 在调用 `run()` 时传入空 `usage_out`，并在 `save()` 时将 `token_usage` 设为 `usage_out[0]`（若非空）或 None（若空）。

#### Scenario: usage 透传到 save
- **WHEN** run 完成后 usage_out 含 `(p, c)`
- **THEN** normalizer 调用 `save(..., token_usage=(p, c))`

#### Scenario: usage 为空时传 None
- **WHEN** run 完成后 usage_out 为空
- **THEN** normalizer 调用 `save(..., token_usage=None)`，不累计 token
