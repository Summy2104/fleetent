# compression-trace Specification

## Purpose
TBD - created by archiving change compression-trace. Update Purpose after archive.
## Requirements

### Requirement: 每次压缩写入一条压缩 trace

每次上下文压缩完成时 SHALL 经 `eval_logger` 写入恰好一条 append-only JSONL trace 记录，其 `kind` 字段 MUST 为 `"compression"`，与既有 trace（`agent_run` / `im_message` / `sandbox_exec`）通过 `kind` 区分。压缩的三种返回形态（正常摘要、静态降级、无中段退化）每种 MUST 各自写入一条压缩 trace。

#### Scenario: 正常摘要写入一条压缩 trace
- **WHEN** 一次压缩正常产出摘要消息（`[*头部, 摘要消息, *尾部]`）
- **THEN** 写入恰好一条 `kind: "compression"` 的 trace 记录，且 `outcome` 标记为「正常摘要」

#### Scenario: 静态降级写入一条压缩 trace
- **WHEN** LLM 摘要调用失败，压缩降级为静态保留头尾 + 截断中段
- **THEN** 写入恰好一条 `kind: "compression"` 的 trace 记录，且 `outcome` 标记为「静态降级」

#### Scenario: 无中段退化写入一条压缩 trace
- **WHEN** 头部与尾部已覆盖全部消息、中段为空，压缩退化为不插入摘要
- **THEN** 写入恰好一条 `kind: "compression"` 的 trace 记录，且 `outcome` 标记为「无中段退化」

### Requirement: 压缩 trace 记录规定的元数据字段

压缩 trace SHALL 记录以下元数据：触发原因、结果类型、压缩前后的 token 数与消息数、保留（头部 + 尾部）与丢弃（进摘要的中段）的消息计数、压缩耗时、所使用的摘要模型标识。触发原因 MUST 能区分自动（超 `Tmax` 触发线）、手动（`/compact` 即 `force`）、错误触发（LLM 上下文过长错误入口）三类来源。

#### Scenario: 触发原因区分三类来源
- **WHEN** 压缩分别经自动触发线、手动 `force`、上下文过长错误入口发起
- **THEN** 对应压缩 trace 的触发原因字段分别标记为「自动」「手动」「错误触发」三类可区分的值

#### Scenario: 记录压缩前后 token 与消息数
- **WHEN** 一次压缩把消息从 N 条 / B tokens 压到 M 条 / A tokens
- **THEN** 压缩 trace 同时记录压缩前消息数 N、压缩前 token 数 B、压缩后消息数 M、压缩后 token 数 A

#### Scenario: 记录保留与丢弃范围计数
- **WHEN** 一次压缩保留头部 H 条、尾部 T 条，丢弃（进摘要）中段 D 条
- **THEN** 压缩 trace 记录头部保留计数 H、尾部保留计数 T、丢弃中段计数 D

#### Scenario: 记录压缩耗时与摘要模型
- **WHEN** 一次正常摘要压缩调用了摘要模型并耗时 t 秒
- **THEN** 压缩 trace 记录压缩耗时与所使用的摘要模型标识；当压缩走降级或退化分支未调用摘要模型时，摘要模型字段为空（不写入或记为 null）

### Requirement: 压缩 trace 记录 session 归因键

压缩 trace SHALL 记录 `session_id` 归因键：当压缩入口的调用方（agent_loop）持有 `session_id` 时，该值 MUST 随触发原因经调用链透传并写入压缩 trace；当调用方无 `session_id`（如 CLI 无 session）时，该字段 MUST 省略（不写入），且压缩 MUST NOT 因此报错。`user_id` 与 `agent_name` 同样作为可选归因键，有则记、无则省略。该归因键令一次 run 内多次压缩的 trace 可被聚合到具体 session。

#### Scenario: 携带 session_id 时写入归因键
- **WHEN** agent_loop 持有 `session_id` 并发起一次压缩
- **THEN** 该次压缩 trace 记录该 `session_id` 归因键

#### Scenario: 同一 session 多次压缩的 trace 可据 session_id 聚合
- **WHEN** 同一 session 内发生多次压缩（如自动触发与手动 `force` 各一次）
- **THEN** 这些压缩 trace 均记录相同的 `session_id`，可据此聚合检出该 session 的全部压缩历史

#### Scenario: 无 session_id 时省略归因键不报错
- **WHEN** 压缩入口的调用方未提供 `session_id`（如 CLI 无 session）
- **THEN** 压缩 trace 不写入 `session_id` 字段，压缩正常完成且不报错

### Requirement: 压缩 trace 只记元数据与摘要标识不落原始大对象

压缩 trace MUST NOT 写入原始消息对象内容，也 MUST NOT 写入摘要正文全文。产出摘要的标识 SHALL 以「指纹（摘要正文的稳定短哈希）+ 摘要长度」表达，足以在多条 trace 间判断摘要是否同一 / 是否变化，但不暴露摘要正文。该克制与 `eval_logger` 既有原则（只记元数据、占位原始大对象）一致。

#### Scenario: 不落原始消息内容
- **WHEN** 写入一条压缩 trace
- **THEN** 该 trace 记录不包含被保留或被丢弃消息的原始内容（仅以计数 / token 数表达范围）

#### Scenario: 摘要以指纹加长度标识不落正文
- **WHEN** 一次压缩产出摘要消息
- **THEN** 压缩 trace 记录摘要的稳定指纹与摘要长度，但不包含摘要正文全文

#### Scenario: 同一摘要指纹一致
- **WHEN** 两次压缩产出内容完全相同的摘要正文
- **THEN** 两条压缩 trace 记录的摘要指纹相同（指纹随正文稳定）

### Requirement: 压缩 trace 写入失败不影响压缩主流程

压缩 trace 的写入 MUST NOT 影响压缩本身的正确性与可用性。当 trace 写入抛出异常时，压缩 MUST 仍返回其原本对 LLM 合法的压缩结果序列，且 MUST NOT 将 trace 写入异常向压缩调用方（主循环）抛出；该写入失败 SHALL 被记录（不静默吞异常）。

#### Scenario: trace 写入异常不中断压缩
- **WHEN** 压缩已产出结果序列，但写入压缩 trace 时抛出异常
- **THEN** 压缩仍返回原本的压缩结果序列，不向调用方抛出该异常，写入失败被记录

### Requirement: 压缩 trace 复用统一 trace 出口与可注入路径

压缩 trace SHALL 写入与既有 trace 相同的 append-only JSONL 出口（`eval_logger` 的单一可注入路径常量），不新增独立的 trace 文件、数据库表或其他持久化结构。trace 写入路径 MUST 可在测试中通过注入隔离（monkeypatch 路径常量），MUST NOT 依赖全局可变状态。

#### Scenario: 写入统一 JSONL 出口
- **WHEN** 写入一条压缩 trace
- **THEN** 该记录追加到与 `agent_run` / `im_message` / `sandbox_exec` 相同的 JSONL 出口，可按 `kind == "compression"` 过滤检出全部压缩历史

#### Scenario: 测试中路径可隔离
- **WHEN** 测试将 trace 路径常量注入到临时目录
- **THEN** 压缩 trace 写入该临时路径，不触碰生产数据目录
