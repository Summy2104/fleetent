## ADDED Requirements

### Requirement: 顶层共享模块无 platform 传递泄漏（棘轮清零）
顶层共享模块(如 `fleetent.user_store`)被 agent 运行时模块 import,若其自身 import `fleetent.platform.*`,则构成**传递泄漏**(agent → 共享模块 → platform)。护栏 SHALL 检测此类传递泄漏。已知泄漏集合(`_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 棘轮)SHALL 为**空**——`user_store` 的 platform 依赖已清(见 `user-store`),不再被 pin。护栏 SHALL 为棘轮:任何模块**新引入**传递 platform 泄漏即失败;任何 pin 模块**不再泄漏**也失败(逼集合只减不增)。

#### Scenario: user_store 不再被 pin
- **WHEN** 运行依赖护栏测试
- **THEN** `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 不含 `fleetent.user_store`(集合为空)

#### Scenario: 新传递泄漏被捕获
- **WHEN** 某顶层共享模块新增 `import fleetent.platform.*` 且被 agent 运行时 import
- **THEN** 护栏测试失败并指出该传递泄漏

#### Scenario: 棘轮只减不增
- **WHEN** 某被 pin 的模块已不再 import platform
- **THEN** 护栏测试失败,要求把它移出已知泄漏集合
