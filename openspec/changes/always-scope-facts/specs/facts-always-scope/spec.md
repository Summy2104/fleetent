# facts-always-scope Specification

## Purpose
为 facts 引入 `scope` 字段，区分按需语义召回（`situational`）和无条件注入（`always`）两类 fact。`always` facts 每轮对话无条件注入 system context，不走向量检索；并通过 soft 白名单 + hard 兜底的分层淘汰策略控制数量增长。

## Requirements

### Requirement: Facts schema scope 字段

facts 表 SHALL 包含 `scope TEXT NOT NULL DEFAULT 'situational'`，取值限于 `'situational'` 和 `'always'`。

#### Scenario: Migration adds scope column
- **WHEN** agent_state_migrations 运行到最新版本
- **THEN** `facts` 表包含 `scope` 列，默认值为 `'situational'`

#### Scenario: Existing facts default to situational
- **WHEN** migration 运行后
- **THEN** 原有 facts 记录的 `scope` 均为 `'situational'`（除回填条目外）

#### Scenario: Migration backfills known always relations
- **WHEN** migration 运行后
- **THEN** `relation` 在 `{response_style, tone, format, language, output_format, never_do, always_do, security, approval_required}` 且 `status='active'` 的 facts `scope` 被设为 `'always'`

### Requirement: Always facts 查询

`facts_store` SHALL 提供 `list_always_facts(user_id)` 函数，返回该用户所有 `scope='always' AND status='active'` 的 facts，纯 SQL，不走向量检索，无截断。

#### Scenario: Returns all active always facts
- **WHEN** 调用 `list_always_facts(user_id)`
- **THEN** 返回该用户所有 `scope='always'` 且 `status='active'` 的 facts
- **AND** 不调用向量后端

#### Scenario: Returns empty list when no always facts
- **WHEN** 用户无 `scope='always'` facts
- **THEN** `list_always_facts()` 返回空列表

### Requirement: Always facts 软上限淘汰

写入新 `scope='always'` fact 时，若 soft 池（`relation` 在 SOFT_RELATIONS 白名单内的 always active facts）已达上限（15 条），系统 SHALL 将最旧（`updated_at ASC`）的 soft fact retract，再写入新条目。

#### Scenario: Soft pool within limit — no eviction
- **WHEN** soft 池条数 < 15
- **THEN** 新 always soft fact 直接写入，不触发淘汰

#### Scenario: Soft pool at limit — evict oldest
- **WHEN** soft 池条数 = 15，写入新 always soft fact
- **THEN** `updated_at` 最旧的 soft fact 被 retract
- **AND** 新 fact 写入成功

#### Scenario: Hard facts never evicted
- **WHEN** hard fact（`relation` 不在 SOFT_RELATIONS 白名单内）写入
- **THEN** 无论 soft 池数量，hard facts 不参与淘汰计数，也不被淘汰

#### Scenario: Unknown relation defaults to hard
- **WHEN** 写入 `scope='always'` fact 且 `relation` 不在 SOFT_RELATIONS 白名单也不在显式 hard 清单
- **THEN** 该 fact 视为 hard，不参与软淘汰

### Requirement: Always facts 不走向量

`scope='always'` facts 写入时 SHALL 仍 upsert 向量索引（保持一致性），但 `list_always_facts()` 检索路径 MUST NOT 调用向量后端，不更新 `access_count`。

#### Scenario: list_always_facts skips vector backend
- **WHEN** 调用 `list_always_facts()`
- **THEN** 向量后端未被调用
- **AND** facts 的 `access_count` 不变
