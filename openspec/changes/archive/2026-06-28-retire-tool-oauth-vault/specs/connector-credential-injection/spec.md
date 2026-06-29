## ADDED Requirements

### Requirement: seam 在 vault 退役后存续且安全降级
`connectors.py` seam（`get_credential` / `Credential` / `NeedsConsent` / `CredentialError` / `set_provider` / `_default_provider`）与 `tools/registry.py` 的 `@tool(connector=)` 通道 SHALL 在工具 OAuth Vault 退役后**原样保留**——本 change 移除的是 platform 侧 vault 实现与注入，而非 agent 侧 seam 本身（"挪实现到 agent 侧、非撤能力"）。

平台 SHALL NOT 再调用 `connectors.set_provider(...)` 注入 vault provider。无任何 provider 注入时，`get_credential` MUST 经 `_default_provider` 返回 `NeedsConsent`（不得抛错、不得崩溃），使声明 connector 的工具优雅短路而非中断 agent 运行。该降级 MUST 在"无 platform、platform DB 表不存在"环境下成立，保证 `fleetent agent run` 验证基线。

将来 agent 侧实现工具凭证时，SHALL 经同一 `set_provider` seam 注入，无需改动调用方与 `@tool(connector=)` 声明。

#### Scenario: 未注入 provider 时安全降级
- **WHEN** vault 退役后、无 agent 侧 provider 注入，一个声明 `@tool(connector="github")` 的工具被调度
- **THEN** `get_credential` 经 `_default_provider` 返回 `NeedsConsent`，工具短路返回 consent 提示，agent 运行不中断、不抛异常

#### Scenario: seam 在无 platform 环境下不崩
- **WHEN** 在无 platform、管理库表不存在的环境运行 `fleetent agent run`
- **THEN** `connectors` seam 可正常 import 与调用，凭证类工具降级为 `NeedsConsent`，对话正常完成

#### Scenario: 将来 agent 侧 provider 可经同一 seam 接入
- **WHEN** agent 侧实现一个凭证 provider 并调用 `connectors.set_provider(provider)`
- **THEN** 后续 `get_credential` 委派该 provider，无需改动 `@tool(connector=)` 声明或 dispatch 调用方
