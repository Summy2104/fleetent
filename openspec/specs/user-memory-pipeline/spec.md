# user-memory-pipeline Specification

## Purpose
定义用户记忆的写入流水线：每轮对话后由 LLM 提取三元组（extract_facts）、将 relation 归并到规范化词表（resolve_relation）、对冲突并发裁决（classify_relation）、再以单事务原子提交（commit_facts）。

## Requirements

### Requirement: extract_facts — LLM 提取三元组
系统 SHALL 在每轮对话结束后，以 user+assistant 对话内容为输入，调用 LLM 提取零到多条原始三元组（RawFact）。

RawFact 结构：`{subject: str, relation: str, object: str, valid_until: str | None}`
- `subject` 通常为 "user"，也可为对话中提及的第三方实体
- `relation` 为 LLM 自由生成的原始 relation 名（后续 resolve_relation 归并）
- `object` 为关系的值
- `valid_until` 为 ISO-8601 日期字符串（当用户提及"今天"、"本周"、"明天"等显式时间边界时填写），否则 NULL

提取 prompt 须指导 LLM：
- 只提取显式的、可持久的用户事实（排除临时询问、假设性表达）
- 当对话无新事实时返回空列表
- 每条 fact 须有 valid_until 判断

#### Scenario: 正常提取单条事实
- **WHEN** 用户说 "我是一名 Python 开发者"
- **THEN** extract_facts 返回 `[{subject:"user", relation:"is_role", object:"Python 开发者", valid_until:null}]`

#### Scenario: 提取带时间边界的事实
- **WHEN** 用户说 "我今天要参加一个技术分享"
- **THEN** extract_facts 返回包含 `valid_until = <当日 23:59:59 UTC ISO-8601>` 的 fact

#### Scenario: 对话无新事实
- **WHEN** 用户问 "今天天气怎么样"
- **THEN** extract_facts 返回空列表，不调用后续 resolve_relation / classify_relation

#### Scenario: LLM 输出格式校验
- **WHEN** LLM 输出不符合 RawFact 结构
- **THEN** 该条 fact 被跳过并记录 warning 日志，不影响其余条目处理

### Requirement: resolve_relation — relation 归并到词表
系统 SHALL 将 RawFact.relation 归并到 relation_clusters 词表中的规范化词条。

归并逻辑：
1. 若 relation_clusters 为空或词条少于 2 条，跳过向量相似度计算，直接以原始 relation 名查询（精确匹配）
2. 计算 RawFact.relation 的向量；与词表所有词条的 embedding 计算余弦相似度
3. 最高相似度 >= 0.90：使用该词条，继承其 cardinality
4. 最高相似度 < 0.90：在 relation_clusters 中插入新词条（cardinality 由 LLM 同步判定）

返回 ResolvedFact：`{...RawFact, relation: <规范化>, cardinality: Literal['single','multi']}`

#### Scenario: 同义 relation 归并
- **WHEN** RawFact.relation = "uses_language"，词表已有 "prefers_language"，余弦相似度 0.93
- **THEN** ResolvedFact.relation = "prefers_language"，cardinality = "single"

#### Scenario: 新 relation 自动创建
- **WHEN** RawFact.relation = "mentors"，与所有词条最高余弦 0.72
- **THEN** relation_clusters 新增 "mentors" 词条，cardinality 由 LLM 判定（返回 'multi'）

### Requirement: classify_relation — 并发裁决
系统 SHALL 对每条 ResolvedFact，查询该 user_id + subject + relation 下的 active 事实，并行调用 LLM 进行裁决。

裁决类型：
- `Equivalent`：新 object 与旧 object 语义等价 → 跳过（不插入新行）
- `Contradict`：新 object 与旧 object 语义矛盾 → 替换（旧→superseded，插新行）
- `NewSubsumed`：新 object 是旧 object 的子集（旧更宽泛）→ 跳过
- `Subsumes`：新 object 是旧 object 的超集（新更宽泛）→ 暂按 Orthogonal 处理
- `Orthogonal`：与所有旧 object 无关 → 直接插入新行

当 cardinality = single 时：
- 若存在 active 旧事实，Contradict 和 Orthogonal 都触发替换（旧→superseded，插新行）
- Equivalent 跳过

当 cardinality = multi 时：
- 对每条 active 旧事实独立裁决
- Contradict：仅 supersede 该条旧事实，插新行
- Orthogonal：直接插新行，旧事实不变
- Equivalent：跳过

#### Scenario: single relation 旧值被替换
- **WHEN** user_id=u1, subject=user, relation=is_role, cardinality=single，已有 active fact "Java 开发者"，新 fact object="Go 开发者"
- **THEN** 旧 fact status → superseded；新 fact 插入；fact_edges 记录 supersedes edge

#### Scenario: multi relation 新值并存
- **WHEN** relation=has_skill，已有 active fact "Python"，新 fact object="Rust"，裁决为 Orthogonal
- **THEN** 旧 "Python" fact 保持 active；"Rust" fact 新插入 active

#### Scenario: Equivalent 裁决跳过
- **WHEN** 新 object "Python" 与已有 active fact "Python 编程语言" 裁决为 Equivalent
- **THEN** 不插入新行，不更新任何字段

#### Scenario: classify 并发执行
- **WHEN** extract_facts 返回 5 条 ResolvedFact
- **THEN** 5 条 classify_relation 调用并发执行（任意顺序），互不阻塞

### Requirement: commit_facts — 事务原子提交
系统 SHALL 在单个 SQLite 事务中完成所有 fact 变更（status 更新 + 新行插入 + fact_edges 插入）。

向量 upsert（VectorBackend）在事务提交后异步执行，写失败只记录 warning，不回滚 SQL 事务。

#### Scenario: 事务回滚
- **WHEN** commit_facts 执行过程中抛出异常
- **THEN** 该轮所有 fact 变更全部回滚（SQLite 事务保证）；向量索引不受影响

#### Scenario: 向量 upsert 失败不回滚 SQL
- **WHEN** SQL 事务提交成功，向量 upsert 网络超时
- **THEN** facts 表变更已持久化；warning 日志记录向量同步失败；下次检索前可通过重建索引修复
