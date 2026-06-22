## ADDED Requirements

### Requirement: 一次性 CLI 经 Principal 调用 agent loop

`fleetent "<prompt>"` 一次性入口(`run_sync` → `_run`)SHALL 以 `principal=Principal(user_id=..., tenant_id="default")` 调用 `loop.run()`,SHALL NOT 传 `run()` 不接受的 `user_id` 关键字。`run()` / `run_stream()` 的签名(收 `principal`)SHALL 不变。

#### Scenario: 一次性入口真实跑通

- **WHEN** 执行 `fleetent "What is 7*8?"`(LLM 在 `get_client_and_config` 边界打桩)
- **THEN** `_run → run()` 真实执行返回回复,**不抛 `TypeError: run() got an unexpected keyword argument`**

#### Scenario: run 签名不变

- **WHEN** 检视 `loop.run` / `loop.run_stream` 签名
- **THEN** 仍收 `principal: Principal | None`;改的是一次性调用方,不是 run 本身

### Requirement: 真实入口冒烟覆盖一次性路径

集成测试 SHALL 覆盖一次性 `run_sync` 的**真实** `run()` 调用——在 `get_client_and_config` 边界打桩 LLM,**不得 mock `loop.run` 本身**(否则绕过入口签名)。

#### Scenario: 冒烟执行真实 run() 而非 mock 它

- **WHEN** 一次性入口冒烟运行
- **THEN** 它 patch `get_client_and_config`(LLM 边界),`_run → run()` 真实执行;若入口与 run 签名不匹配,测试 SHALL fail
