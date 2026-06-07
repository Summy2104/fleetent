## ADDED Requirements

### Requirement: session 元数据批量删除

系统 SHALL 提供 `delete(session_id)` 和 `delete_batch(session_ids)` 函数，删除 `sessions` 表中指定 session 的元数据行。`delete_batch` MUST 在单个事务中删除所有指定行。删除不存在的 session_id MUST NOT 报错（幂等）。

#### Scenario: 删除单行元数据
- **WHEN** 以存在的 `session_id` 调用 `delete(session_id)`
- **THEN** `sessions` 表中该行被删除，后续 `get(session_id)` 返回 None

#### Scenario: 批量删除多行元数据
- **WHEN** 以多个 `session_id` 调用 `delete_batch(session_ids)`
- **THEN** 所有指定行在单个事务中被删除

#### Scenario: 删除不存在的 session_id 幂等
- **WHEN** 以不存在的 `session_id` 调用 `delete` 或 `delete_batch`
- **THEN** 调用正常返回，不抛出异常，表数据不受影响

## MODIFIED Requirements

### Requirement: session 元数据查询

系统 SHALL 提供按 session 与按 user 的元数据查询。`get(session_id)` MUST 在不存在时返回 None；`list_by_user(user_id, limit=50, before_updated_at=None)` MUST 返回该 user 的 session 元数据，按最后活跃时间倒序排列，支持游标分页：当 `before_updated_at` 非 None 时，MUST 只返回 `updated_at < before_updated_at` 的记录；`limit` MUST 限制返回行数上限，默认 50。

#### Scenario: 查询单个 session 元数据
- **WHEN** 以存在的 `session_id` 查询元数据
- **THEN** 返回该 session 的元数据；以不存在的 `session_id` 查询时返回 None

#### Scenario: 按 user 列出 session 并按活跃时间倒序（默认分页）
- **WHEN** 调用 `list_by_user(user_id)` 不传游标参数
- **THEN** 返回该 user 最近 50 条 session 元数据，最近活跃的排在最前

#### Scenario: 游标分页获取下一页
- **WHEN** 以上一页最后一条的 `updated_at` 作为 `before_updated_at` 调用 `list_by_user`
- **THEN** 返回 `updated_at` 早于该游标值的下一页记录，不重复上一页内容

#### Scenario: limit 参数截断结果
- **WHEN** 调用 `list_by_user(user_id, limit=10)`
- **THEN** 返回记录数不超过 10 条
