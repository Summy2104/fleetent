## MODIFIED Requirements

### Requirement: Key resolution enforces validity
Resolving a user by API key SHALL succeed only when the key exists, is not revoked, is not expired, and its owning user is not `blocked`. 该解析 SHALL 经基座 `Identity` 端口的适配器暴露（见 `identity-port`）；**agent 侧（standalone）解析适配器 MUST NOT `import fleetent.platform.*`**——platform 专属的 `api_keys` 表解析仅存在于 platform 侧适配器。`user_store` 自身 MUST NOT 无条件 import platform 来完成认证（根除 #1 泄漏）。有效性语义（存在/未吊销/未过期/owner 非 blocked 才成功）不变。

#### Scenario: Valid key resolves
- **WHEN** a non-revoked, non-expired key of an active user is presented
- **THEN** the owning `User` is returned

#### Scenario: Revoked/expired/blocked rejected
- **WHEN** the key is revoked, expired, or its user is `blocked`
- **THEN** resolution returns `None` (authentication fails)

#### Scenario: agent 侧解析不依赖 platform
- **WHEN** standalone agent（无 platform、platform 表不存在）解析 bearer key
- **THEN** 解析经 agent 侧适配器完成，全程不 `import fleetent.platform.*`、不查询 platform 表
