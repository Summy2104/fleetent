## ADDED Requirements

### Requirement: 服务账号创建 HTTP API

平台 SHALL 在 `POST /admin/service-principals` 暴露服务账号创建端点，包装 `user_store.create_user(name)`：创建用户并即时签发一把 `ma-` API key（scope `["*"]`）。明文 key MUST 仅在创建响应中一次性返回（`api_key_plaintext_once`），之后不可再查。端点 MUST 要求 admin 角色并写审计。该端点等价于 CLI `create-user` 的 bootstrap 路径（区别于 `POST /admin/users` 的 web 用户创建——后者需 email、不发 key）。

#### Scenario: 创建服务账号并一次性返回 key

- **WHEN** admin 调用 `POST /admin/service-principals`，body 含 `name`
- **THEN** 系统创建用户、签发 `ma-` key，响应含 `api_key_plaintext_once`（明文，仅此一次）
- **AND** 后续查询该用户的 key 列表不再返回明文

#### Scenario: 与 web 用户创建语义区分

- **WHEN** 对比 `POST /admin/service-principals` 与 `POST /admin/users`
- **THEN** 前者建服务账号即发 key（无需 email），后者建 web 用户（需 email、不发 key）

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用该端点
- **THEN** 系统返回 403

### Requirement: 按用户原子轮换 key HTTP API

平台 SHALL 在 `POST /admin/users/{user_id}/rotate-key` 暴露按用户原子轮换端点，包装 `user_store.rotate_key(user_id)`：撤销该用户全部 active key 并签发一把新 key。新 key 明文 MUST 一次性返回。user 不存在 SHALL 返回 404。端点 MUST 要求 admin 角色并写审计。等价于 CLI `rotate-key`。

#### Scenario: 轮换撤销旧 key 并发新 key

- **WHEN** 某用户持有 active key A、B，admin 调用 `POST /admin/users/{user_id}/rotate-key`
- **THEN** A、B 立即失效，系统签发一把新 key，响应含明文（仅此一次）

#### Scenario: 轮换不存在的用户返回 404

- **WHEN** admin 以不存在的 `user_id` 调用
- **THEN** 系统返回 404，不签发任何 key

#### Scenario: 非 admin 访问被拒绝

- **WHEN** 非 admin 角色用户调用该端点
- **THEN** 系统返回 403
