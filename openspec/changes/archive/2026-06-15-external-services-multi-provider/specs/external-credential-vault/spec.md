# external-credential-vault Specification

## ADDED Requirements

### Requirement: provider 适配层支持多服务

系统 SHALL 提供一个 `ServiceProvider` 适配接口，封装各外部服务在以下环节的差异：构造授权 URL、code→token 交换、token→工具 client 构造、scope 规范化。consent 流与 Vault provider SHALL 经按 `external_services.kind` 选型的适配完成上述环节。新增一个服务 SHALL 只需注册（`external_services` 一行）+ 提供其适配，MUST NOT 改动 dispatch / consent 核心或 seam 契约。适配层 MUST NOT 持有或存储 `client_secret`（仍走 env）。

#### Scenario: 按 kind 选型适配
- **WHEN** 一个 `kind="google_drive"` 的服务发起 consent
- **THEN** 经 google_drive 适配构造授权 URL 与 token 交换；`kind="github"` 的服务则经 github 适配，二者互不影响

#### Scenario: 新增服务不改核心
- **WHEN** 注册一个新服务并提供其适配
- **THEN** 该服务可被授权与解析，未改动 dispatch / consent 核心代码与 `get_credential` 契约

#### Scenario: 多服务并存解析
- **WHEN** 同一用户分别授权了 google-drive 与 github
- **THEN** 两个服务各自经其适配解析出独立 `Credential`，互不串用
