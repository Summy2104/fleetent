## ADDED Requirements

### Requirement: 基于总大小与数量上限的容量判定

session 容量管理 SHALL 支持两个独立上限：session 文件总大小上限与 session 最大保留数量。当 session 文件总大小超过总大小上限，或 session 总数超过最大数量上限时，容量管理 MUST 判定为超限并触发淘汰。

#### Scenario: 总大小超限触发淘汰
- **WHEN** 所有 session 文件总大小超过配置的总大小上限
- **THEN** 容量管理判定超限并进入淘汰流程

#### Scenario: 数量超限触发淘汰
- **WHEN** session 总数超过配置的最大保留数量
- **THEN** 容量管理判定超限并进入淘汰流程

#### Scenario: 均未超限时不淘汰
- **WHEN** session 总大小与总数均未超过各自上限
- **THEN** 容量管理不删除任何 session，返回空的被删列表

### Requirement: LRU 最旧优先淘汰至回落阈值

超限时，容量管理 SHALL 按最后活跃时间（文件 mtime）升序、最久未活跃优先删除 session 文件，并 MUST 持续删除直到总大小与总数两个有效上限均回落到阈值以内。淘汰 MUST 跳过原子写产生的 `.json.tmp` 临时文件，返回被删除的 session_id 列表。

#### Scenario: 按最旧优先淘汰
- **WHEN** session 超限需要淘汰
- **THEN** 最后活跃时间最早的 session 被优先删除，最近活跃的 session 保留

#### Scenario: 淘汰至双约束满足后停止
- **WHEN** 容量管理执行淘汰
- **THEN** 当总大小与总数两个有效上限均不再超限时停止删除，不过度淘汰仍在阈值内的 session

#### Scenario: 不误删临时文件
- **WHEN** 淘汰时目录中存在原子写中间态 `.json.tmp` 文件
- **THEN** 该 `.json.tmp` 文件不被淘汰删除

### Requirement: 上限可配置、可覆盖、可按维度关闭

总大小上限与最大数量上限 SHALL 来自 `Settings`（env 可配，分别有默认值）。淘汰函数 MUST 接受可选参数覆盖配置；当某维度上限配置为关闭值（如 0）时，该维度 MUST NOT 触发淘汰、也 MUST NOT 作为停止条件。

#### Scenario: 调用参数覆盖配置
- **WHEN** 调用淘汰函数时显式传入总大小或数量上限
- **THEN** 淘汰使用传入的上限，而非 Settings 配置值

#### Scenario: 关闭某一维度上限
- **WHEN** 某维度上限被配置为关闭值
- **THEN** 容量管理不依据该维度判定超限或停止，仅按另一个有效维度淘汰；若两维度均关闭则不淘汰任何 session

### Requirement: 删除容错与日志记录

淘汰过程 SHALL 对单个文件删除失败容错；某文件删除失败 MUST 不中断整批淘汰，MUST 记录警告日志后继续。淘汰操作 MUST 记录在系统日志中，包含触发原因（超大小 / 超数量）与被淘汰数量。

#### Scenario: 单个删除失败不中断整批
- **WHEN** 淘汰过程中某个 session 文件删除失败
- **THEN** 该失败被记录为警告日志，淘汰继续处理其余待淘汰文件，不抛出异常中断整批

#### Scenario: 淘汰操作写入系统日志
- **WHEN** 容量管理执行并淘汰了 session
- **THEN** 系统日志记录触发原因与被淘汰的 session 汇总信息

### Requirement: 容量管理由内置维护触发驱动

容量管理 SHALL 由 `session-ttl-cleanup` 定义的内置维护触发(`save()` 机会式、时间门控)在 TTL 清理之后驱动执行,无需外部调度。

> 注:review 决定(2026-05-31)将容量管理并入该内置维护触发,取代原"触发器留后续接 cron"。

#### Scenario: 维护触发时执行容量管理
- **WHEN** 内置维护触发在某次 `save()` 后执行(门控开启)
- **THEN** 先执行 TTL 过期清理,再执行容量淘汰,两者在同一次门控维护内完成
