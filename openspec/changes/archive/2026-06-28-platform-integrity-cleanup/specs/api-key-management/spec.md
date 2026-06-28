# api-key-management

## ADDED Requirements

### Requirement: api_keys.user_id 外键完整性
`api_keys.user_id` **MUST** 经外键 `→ users(id) ON DELETE CASCADE` 约束。删除一个 user 时,其名下全部 api_keys 行随之级联删除,不产生 user_id 指向已不存在 user 的孤儿 key。此为结构性完整性,独立于认证期的"owner blocked → 401"运行时校验。

#### Scenario: 删用户级联清 key
- **WHEN** 删除一个名下有若干 api_keys 的 user
- **THEN** 该 user 的全部 api_keys 行随删除级联清除,管理库中不留 user_id 指向该已删 user 的 key 行

#### Scenario: 无孤儿 key 残留
- **WHEN** 对管理库执行完整性审计(api_keys JOIN users)
- **THEN** 不存在 user_id 无法在 users 中匹配的 api_keys 行
