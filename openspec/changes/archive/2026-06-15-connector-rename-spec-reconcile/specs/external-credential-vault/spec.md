# external-credential-vault Specification

## MODIFIED Requirements

### Requirement: 外部服务注册表（单层全局，多协议）

系统 SHALL 提供一张外部服务注册表 `external_services`，登记每个可被工具访问的外部服务的非密配置：`service_id`（主键）、`protocol`（`oauth2` | `apikey`）、`authorize_url`、`token_url`、`client_id`、`scopes`、`enabled`、时间戳。注册表 SHALL 为**单层全局**（每个 `service_id` 仅一条，无 per-agent 覆盖层）。`client_secret` MUST NOT 存入该表（走 env / `agent_secrets`）。SQL MUST 用 named parameters 经 store 边界，schema MUST 由迁移建立，无 ORM。

> P7 勘误：原 spec 列出了不存在的 `kind` 列（已在 P6 re-baseline 中确认 `external_services` 表无此列，工厂路由键改用 `service_id`）；`protocol` 枚举值改为与代码一致的 `oauth2` / `apikey`（原写 `oauth2_authcode` / `api_key`）。

#### Scenario: 注册并读回一个服务
- **WHEN** 管理员注册一个 `service_id="google-drive"`、`protocol="oauth2"` 的服务
- **THEN** 该服务出现在注册表中，可读回其 authorize/token endpoint、`client_id`、scopes，且不含任何 `client_secret`

#### Scenario: service_id 全局唯一
- **WHEN** 已存在 `service_id="google-drive"` 时再次以同 id 注册
- **THEN** store 拒绝重复（无 per-agent 维度可区分）
