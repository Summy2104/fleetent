## ADDED Requirements

### Requirement: 长短期记忆区分
系统 SHALL 以 `expires_at` 字段区分长期与短期记忆：
- `expires_at IS NULL`：长期记忆，不受自动消亡机制影响
- `expires_at IS NOT NULL`：短期记忆，受生命周期机制管理

新 fact 写入时默认 expires_at 规则：
- 若 valid_until 不为 NULL：`expires_at = valid_until`
- 若 valid_until 为 NULL：`expires_at = now + 30 days`

#### Scenario: 带时间边界的 fact 写入短期
- **WHEN** commit_facts 写入 valid_until = "2026-06-24T23:59:59Z" 的 fact
- **THEN** expires_at = "2026-06-24T23:59:59Z"，为短期记忆

#### Scenario: 无时间边界的 fact 默认 30 天
- **WHEN** commit_facts 写入 valid_until = NULL 的 fact
- **THEN** expires_at = 写入时刻 + 30 天，为短期记忆

---

### Requirement: 短期记忆自动消亡
系统 SHALL 提供后台 job `archive_expired_facts`，定期 archive 以下短期记忆：
- `expires_at <= now`（有效期已过）
- `last_accessed_at <= now - 30 days`（30 天内未被检索命中，即使 expires_at 未到）
  - `last_accessed_at IS NULL` 的短期记忆，以 `created_at` 替代计算 30 天窗口

job 执行时 UPDATE `status = 'archived', updated_at = now` WHERE 满足上述任一条件 AND status = 'active'。
向量后端对应条目异步删除。

#### Scenario: expires_at 到期 archive
- **WHEN** archive_expired_facts 运行时某 short-term fact 的 expires_at 早于 now
- **THEN** 该 fact status 变为 archived；向量索引中对应条目删除

#### Scenario: 30 天未命中 archive
- **WHEN** short-term fact 的 last_accessed_at = 35 天前，expires_at = 未来 10 天
- **THEN** archive_expired_facts 将该 fact status 变为 archived（last_accessed_at 触发优先）

#### Scenario: 长期记忆不受影响
- **WHEN** archive_expired_facts 运行时某 fact 的 expires_at IS NULL
- **THEN** 该 fact status 不变

---

### Requirement: 自动升级为长期记忆
系统 SHALL 在检索命中更新 access_count 和 first_accessed_at 后，判断是否满足升级条件。

升级条件（两者同时满足）：
- `access_count >= 10`
- `first_accessed_at <= now - 14 days`（首次命中至今已满 14 天）

满足升级条件时：将 `expires_at` 设为 NULL（变为长期记忆），更新 `updated_at`。

#### Scenario: 达到升级条件
- **WHEN** fact 的 access_count 达到 10，且 first_accessed_at 为 15 天前
- **THEN** fact.expires_at 被设为 NULL；该 fact 成为长期记忆

#### Scenario: 频繁访问但时间不足不升级
- **WHEN** fact 的 access_count = 15，first_accessed_at = 5 天前
- **THEN** fact.expires_at 保持不变（不满足 14 天条件）

#### Scenario: 时间足够但访问不足不升级
- **WHEN** fact 的 access_count = 3，first_accessed_at = 20 天前
- **THEN** fact.expires_at 保持不变（不满足 access_count 条件）

---

### Requirement: 用户主动 pin（设为长期记忆）
系统 SHALL 提供 `pin_fact(fact_id)` 操作，将指定 fact 的 `expires_at` 设为 NULL。

pin 操作：
- 仅对 status = 'active' 的 fact 有效
- 设置 `expires_at = NULL`，更新 `updated_at`
- 不修改 access_count、first_accessed_at 等其他字段

#### Scenario: 用户 pin 一条短期记忆
- **WHEN** 用户说 "记住这个" 指向某条 short-term fact，系统调用 pin_fact
- **THEN** fact.expires_at = NULL；该 fact 成为长期记忆；下次运行 archive_expired_facts 不影响它

#### Scenario: pin 非 active fact 报错
- **WHEN** 调用 pin_fact 指向 status = 'archived' 的 fact
- **THEN** 抛出 ValueError("cannot pin non-active fact")

---

### Requirement: 用户主动 retract（归档事实）
系统 SHALL 提供 `retract_fact(fact_id)` 和 `retract_by_relation(user_id, subject, relation)` 操作。

`retract_fact`：将指定 fact status 设为 'retracted'，向量索引删除对应条目。
`retract_by_relation`：将 user_id + subject + relation 下所有 active fact status 设为 'retracted'。

retract 语义区别于 archive：retract 表示用户主动否认（如 "我不再用 Java 了"），archive 表示自然过期。

#### Scenario: retract 单条 fact
- **WHEN** 调用 retract_fact(fact_id="abc")
- **THEN** fact status = 'retracted'；向量索引中 "abc" 被删除；fact 行保留（never hard-delete）

#### Scenario: retract 整个 relation
- **WHEN** 用户说 "我不再做 Python 了"，系统调用 retract_by_relation(user_id, "user", "has_skill") with object filter "Python"
- **THEN** 所有匹配的 active fact status = 'retracted'

---

### Requirement: 后台 job 注册
系统 SHALL 在 agent boot 时将 `archive_expired_facts` 注册为定时任务，默认间隔 1 小时。

job 执行失败时：记录 error 日志，不影响 agent 正常运行（舱壁化）。

#### Scenario: job 定时执行
- **WHEN** agent boot 完成，1 小时后
- **THEN** archive_expired_facts 自动运行，过期短期记忆被 archived
