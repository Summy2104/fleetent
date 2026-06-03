# compression-incremental-summary Specification

## Purpose
TBD - created by archiving change compression-incremental-summary. Update Purpose after archive.
## Requirements
### Requirement: 多次压缩增量摘要

当会话已存在上一次压缩产生的累积摘要消息时，本次压缩 SHALL 从该摘要消息提取累积摘要文本 `prev_summary`，与当前中段（上一条摘要消息之后、尾部之前的消息）合并为新的累积摘要。由于上一次压缩已物理移除被摘的旧中段，当前中段天然即「新增」部分，压缩 MUST NOT 重新摘要已被 `prev_summary` 覆盖的旧内容，且 MUST NOT 依赖任何独立的「已摘覆盖边界」标记。当不存在累积摘要消息时，压缩 MUST 退化为对全部中段的完整摘要。

#### Scenario: 已有摘要时合并 prev_summary 与当前中段
- **WHEN** 会话已存在上一次压缩的累积摘要消息，本次再次触发压缩
- **THEN** 从该摘要消息提取的 `prev_summary` 与当前中段一并交给 LLM 合并为新累积摘要，已被 `prev_summary` 覆盖的旧内容不被重新摘要

#### Scenario: 无累积摘要时全量摘要
- **WHEN** 会话不存在任何累积摘要消息而触发压缩
- **THEN** 对全部中段消息执行完整摘要

#### Scenario: 累积摘要不无限增长
- **WHEN** 同一会话经历多次增量压缩
- **THEN** 累积摘要受长度上界约束，不会增长到自身超过压缩目标线投影

### Requirement: 摘要文本标注来源

压缩产出的摘要消息文本 MUST 显式标注其为「历史对话摘要，仅供参考」，声明该内容为早期对话的压缩、不是新的用户指令，以防止 AI 将摘要内容误作当前要执行的命令。

#### Scenario: 摘要消息含来源标注
- **WHEN** 压缩产出一条摘要消息
- **THEN** 该消息文本包含「历史对话摘要，仅供参考」含义的标注，声明其非新指令

### Requirement: 摘要失败降级不崩溃

当 LLM 摘要调用失败（异常、超时或空响应）时，压缩 MUST 降级为静态保留头尾 + 截断中段的纯规则处理（不调用 LLM），返回对 LLM 合法且可继续使用的消息序列。压缩 MUST NOT 因摘要失败而向主循环抛出异常；降级事件 MUST 被记录（不静默吞异常）。

#### Scenario: 摘要调用异常时静态降级
- **WHEN** LLM 摘要调用抛出异常
- **THEN** 压缩降级为保留头尾、截断中段，返回合法序列，不抛异常

#### Scenario: 摘要返回空时静态降级
- **WHEN** LLM 摘要调用返回空响应
- **THEN** 压缩降级为保留头尾、截断中段，返回合法序列，不抛异常

### Requirement: 累积摘要随 session 持久化

累积摘要 SHALL 以一条普通 system 摘要消息（含来源标注前缀 + 摘要正文）的形态随既有 session 持久化往返，使 session 重新加载后下一次压缩能识别该摘要消息、提取 `prev_summary` 并在其基础上继续增量，而非从头重摘。本能力 MUST NOT 新增独立持久化结构（不引入伴随文件、数据库表或消息内边界字段），MUST NOT 依赖全局可变状态，且持久化路径 MUST 可在测试中通过注入隔离。

#### Scenario: 持久化往返后继续增量
- **WHEN** 一次压缩产生累积摘要消息并经持久化保存后重新加载，会话再次触发压缩
- **THEN** 本次压缩识别到上一条累积摘要消息、提取 `prev_summary` 并在其基础上增量，不重摘已覆盖的旧内容

#### Scenario: 不新增持久化结构
- **WHEN** 累积摘要随 session 持久化
- **THEN** 仅复用既有整列表持久化（摘要为普通 system 消息），不产生伴随文件 / 数据库表 / 消息内边界字段

### Requirement: 错误触发压缩沿用增量摘要与降级

经「LLM 上下文过长错误」入口（AR12 已提供的 `compress_for_context_overflow`，本 change 不重定义其触发与目标线语义）触发的压缩，其摘要 SHALL 沿用本 capability 的增量摘要语义（存在累积摘要消息时合并 `prev_summary` 与当前中段）并附来源标注；若本次 LLM 摘要调用失败，MUST 走静态降级返回对 LLM 合法的序列供调用方重试，而非抛出异常。

#### Scenario: 错误触发压缩沿用增量摘要
- **WHEN** 经上下文过长错误入口触发压缩且会话已存在累积摘要消息
- **THEN** 该次压缩按增量语义合并 `prev_summary` 与当前中段，产出附来源标注的摘要消息

#### Scenario: 错误触发压缩时摘要失败仍返回可重试序列
- **WHEN** 因上下文过长错误请求压缩，但本次 LLM 摘要调用失败
- **THEN** 压缩降级为静态保留头尾 + 截断中段，返回合法序列供调用方重试，不抛异常

