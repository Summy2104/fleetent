## MODIFIED Requirements

### Requirement: Expanded users schema
The `users` table SHALL carry `email`, `password_hash`, `role` (default `viewer`), `status` (default `active`; one of `active`/`disabled`/`blocked`), and `must_reset` (default 0)，schema 由管理库 Alembic 迁移维护（非 store 自建）。`users` 表 SHALL NOT 含 `api_key` 列——API key 唯一真相源为 `api_keys` 表。

`email` SHALL 保持**可空**（内置 admin / service principal / 纯 IM 用户可无 email），但当存在时 SHALL **规范化为 `lower(trim(email))` 后写入**，并在租户内**唯一**：管理库 SHALL 维护 partial `UNIQUE(tenant_id, email)`（仅 `email IS NOT NULL` 时生效）。`email` 因此是**租户内跨渠道 join key**。`get_by_email` SHALL 按 **tenant 范围 + 规范化** 匹配（同一规范化 email 在不同租户是不同的人）。

#### Scenario: Columns present at head
- **WHEN** 管理库 Alembic 迁移运行到最新版本
- **THEN** `users` has `email`, `password_hash`, `role`, `status`, `must_reset`
- **AND** `users` 不含 `api_key` 列

#### Scenario: Idempotent migration on legacy db
- **WHEN** an older `users` table without these columns is initialized
- **THEN** the columns are added with defaults and existing rows are preserved

#### Scenario: 存量明文 key 经回填迁移
- **WHEN** 含 `users.api_key` 明文值的旧库升级到最新版本
- **THEN** 每个明文 key 以哈希形式回填为 `api_keys` 行（scope `["*"]`、无过期、归属同一 user），随后 `api_key` 列被移除，原 key 仍可用于认证

#### Scenario: email 租户内规范化唯一
- **WHEN** 迁移运行到最新版本，且尝试在**同一租户**插入两个规范化后相同的 `email`
- **THEN** partial `UNIQUE(tenant_id, email)` 拒绝第二条；不同租户的相同 email 允许（视为不同的人）

#### Scenario: 大小写/空白不敏感匹配
- **WHEN** 以 `  Alice@Co.com ` 调 `get_by_email`，库中存的是 `alice@co.com`（同租户）
- **THEN** 命中同一 user（规范化为 `lower(trim)` 后比较）

#### Scenario: 无 email 用户不受影响
- **WHEN** 创建无 email 的用户（内置 admin / service principal / 纯 IM）
- **THEN** 正常创建，不参与 email 唯一约束、不参与 email 并号

#### Scenario: 存量重复 email 迁移中止
- **WHEN** 加 partial unique 索引前发现同租户存在规范化后重复的 email
- **THEN** 迁移**报告冲突并中止**，不自动合并任何 user（由运维人工处置）
