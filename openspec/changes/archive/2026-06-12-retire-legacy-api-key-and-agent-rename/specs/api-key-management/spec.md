# api-key-management Delta

## ADDED Requirements

### Requirement: 单轨真相源与明文禁令
`api_keys` 表 SHALL 是 API key 的唯一持久化真相源（单轨制）。系统任何表 MUST NOT 持久化明文 key——key 以 `key_hash` 哈希入库，明文仅在创建时刻返回调用方一次。认证路径 MUST 全部经 `api_keys` 哈希比对，不存在第二条凭证查找路径。

#### Scenario: 全库无明文 key
- **WHEN** 检查管理库 schema 与写入路径
- **THEN** 除创建时一次性返回外，任何表与日志不持久化明文 key（`users` 表无 key 列）

#### Scenario: 认证单路径
- **WHEN** 任一部署形态（managed / standalone）解析 bearer key
- **THEN** 解析均为 `api_keys` 表的哈希比对，无 fallback 第二来源
