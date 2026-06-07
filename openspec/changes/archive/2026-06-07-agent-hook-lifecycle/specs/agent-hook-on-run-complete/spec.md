## ADDED Requirements

### Requirement: on_run_complete run 完成观测

当 hooks 启用且注册了 `on_run_complete` hook 时，`run()` SHALL 在最终 reply 定稿、`_record_agent_run_completed` 之后、返回前 dispatch `"on_run_complete"` ctx`{reply, stop_reason_name}`；纯观测（审计/计费/通知），不影响 reply。

#### Scenario: hook 观测 run 完成
- **WHEN** `on_run_complete` hook 注册并 hooks 启用
- **THEN** 每次 run() 完成后 hook 被调用，payload 含最终 reply 和 stop reason

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用
- **THEN** run() 行为与未引入本能力时完全一致
