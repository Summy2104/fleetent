## MODIFIED Requirements

### Requirement: LRU 最旧优先淘汰至回落阈值

超限时，容量管理 SHALL 按最后活跃时间（文件 mtime）升序、最久未活跃优先删除 session 文件，并 MUST 持续删除直到总大小与总数两个有效上限均回落到阈值以内。淘汰 MUST 跳过原子写产生的 `.json.tmp` 临时文件，返回被删除的 session_id 列表。淘汰成功删除文件后 MUST 同步删除 `sessions` 表中对应的 index 行；index 行删除失败 MUST 记录 warn 日志，MUST NOT 中断整批淘汰。

#### Scenario: 按最旧优先淘汰
- **WHEN** session 超限需要淘汰
- **THEN** 最后活跃时间最早的 session 被优先删除，最近活跃的 session 保留

#### Scenario: 淘汰同步删除索引行
- **WHEN** `enforce_capacity()` 成功淘汰若干 session 文件
- **THEN** `sessions` 表中对应的 session_id 行被同步删除，后续 `count()` 不再计入这些 session

#### Scenario: 索引删除失败不中断淘汰
- **WHEN** 文件淘汰成功但 `sessions` 表的 index 行删除抛出异常
- **THEN** 该异常被记录为 warn 日志，整批淘汰继续

#### Scenario: 淘汰至双约束满足后停止
- **WHEN** 容量管理执行淘汰
- **THEN** 当总大小与总数两个有效上限均不再超限时停止删除，不过度淘汰仍在阈值内的 session
