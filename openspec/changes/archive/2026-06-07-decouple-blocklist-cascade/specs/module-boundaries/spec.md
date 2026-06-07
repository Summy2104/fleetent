## ADDED Requirements

### Requirement: Agent runtime 不依赖 platform
agent-runtime 模块（`runtime`、`session`、`im_gateway`、`intelligence`、`tools`、`integrations`、`model`、`observability`、`governance`）MUST NOT `import fleetent.platform`。需要协调 platform stores（API 密钥、IM 账号、用户管理等）的编排逻辑 SHALL 落在 platform 层；agent-runtime 模块仅暴露被 platform 调用的 public API 或共享可读存储。

#### Scenario: governance 不 import platform
- **WHEN** 检查 `fleetent.governance` 下任一模块的 import
- **THEN** 不存在对 `fleetent.platform` 的 import

#### Scenario: 级联编排归 platform
- **WHEN** 封禁用户需要吊销其 API 密钥并禁用其 IM 账号（均为 platform-owned 数据）
- **THEN** 该级联编排由 platform 层模块执行，而不是由 governance 模块 import platform store 来执行
