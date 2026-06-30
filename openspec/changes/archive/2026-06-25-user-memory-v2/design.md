## Context

现有用户记忆系统（`src/fleetent/memory/`）以自由文本片段存储信息，模型为 `memory_items` 表 + identity/preferences/context 三分类。核心问题：

- 无结构导致语义去重依赖向量相似度阈值，高则漏存，低则重复累积
- 事实冲突（"我是 Java 开发者" vs "我现在用 Go"）无法追踪，旧事实永久占据检索结果
- 短期与长期记忆无区分，所有记忆同等对待，无自然消亡机制

本次重写将存储单元从自由文本改为三元组（subject, relation, object），引入状态机、生命周期和 supersedes 链，彻底解决上述三个问题。

**范围**：
- `src/fleetent/memory/` 全模块重写
- `agent_state.db`（per-agent 物理库）新增 facts / fact_edges / relation_clusters 三张表
- 现有 `memory_items` / `agent_memory_items` 数据不迁移（新系统从零积累）
- `agent_memory.py`（agent 自身记忆）本次**不动**，与用户记忆分开演进

**约束**：
- 必须遵守 agent→platform 单向依赖契约，memory/ 不得 import platform.*
- 向量后端继续使用现有 `VectorBackend` 抽象，不在 facts 表存 embedding BLOB
- 嵌入式迁移 Y 模式（PRAGMA user_version + MIGRATIONS 列表），脱离 Alembic

---

## Goals / Non-Goals

**Goals:**

- 以三元组取代自由文本，使去重和冲突裁决结构化、可审计
- 引入 cardinality（single/multi）区分"最新值覆盖"关系与"可并存"关系
- 短期记忆靠 last_accessed_at 30 天窗口自然消亡；高频命中自动升级为长期
- 用户可主动 pin（设为长期）或 retract（归档）事实
- valid_until 支持时间边界（"今天"、"本周"等显式有效期）
- max_score < 0.5 时跳过 access 计数，避免不相关对话消耗短期记忆存活时间
- 后台 job 定期 archive 过期短期记忆

**Non-Goals:**

- agent 自身记忆（agent_memory_items）不在本次范围内
- 旧 memory_items 数据迁移
- Subsumes 裁决（语义包含）延后设计，暂按 Orthogonal 处理（两条事实并存）
- 多用户共享记忆 / 跨租户记忆

---

## Decisions

### 1. 存储单元：三元组 (subject, relation, object)

**决策**：每条用户记忆存为 `(user_id, subject, relation, object, cardinality, status, ...)`，主键为 fact_id（UUIDv4）。

**为什么不保留自由文本**：自由文本无法在 SQL 层做 relation 级的 cardinality 判断，向量重复检测在噪声高时误判率高；三元组可在写入时精确匹配 subject+relation，实现"同 relation 覆盖"语义。

**备选**：JSON blob per 记忆条目（半结构化）— 拒绝，因 blob 无法高效按 relation 检索，cardinality 判断仍需应用层全量扫描。

---

### 2. cardinality：single vs multi

**决策**：cardinality 字段随 relation 而定，存储在 relation_clusters 词表，fact 行冗余存一份。

- `single`：新值写入时将同 user+subject+relation 的 active 事实全部移到 superseded 状态，新 fact 记录 supersedes edge
- `multi`：新值写入时先做向量相似度检查，cosine ≥ 0.9 视为重复跳过；否则直接插入新行（与旧行并存）

**为什么**：`is_role` / `prefers_language` 等单值关系天然需要覆盖；`has_skill` / `works_on_project` 等多值关系需要并存。用词表集中管理避免每次写入要重新判断。

---

### 3. relation_clusters 词表（可扩展固定词表）

**决策**：`relation_clusters` 表存储规范化 relation 名和 cardinality。LLM 提取时从词表中选择最接近的 relation（cosine ≥ 0.90）；无匹配则创建新词条（自动扩展）。

**为什么不用纯 LLM 自由生成**：自由生成导致同义词爆炸（`uses_language` / `primary_language` / `codes_in`），词表提供归并锚点。cosine < 0.90 才创建新词表项，阈值防止过度碎片化。

**预置词表**（部分）：
```
is_role          single   # 职业/角色
works_at         single   # 所在公司
located_in       single   # 地点
prefers_language single   # 编程语言偏好
speaks_language  multi    # 口语语言
has_skill        multi    # 技能
works_on_project multi    # 正在做的项目
prefers_tool     multi    # 工具偏好
interested_in    multi    # 感兴趣领域
```

---

### 4. supersedes 链：fact_edges 表，never hard-delete

**决策**：事实只做状态迁移（active → superseded / archived / retracted），物理行永久保留。supersedes 关系存 `fact_edges(from_fact_id, to_fact_id, edge_type)` 表。

**为什么**：用户事实变化应可追溯（"我从 Java 转 Go 是从什么时候开始的"）；hard-delete 丢失历史；soft-delete 在同一表列扩展可审计性较差，单独 edges 表更利于历史查询。

---

### 5. 生命周期：长短期统一，靠 expires_at 区分

**决策**：
- `expires_at IS NULL` = 长期记忆（永不自动消亡）
- `expires_at IS NOT NULL` = 短期记忆，由后台 job 检查：
  - `expires_at` 到期 → archive
  - `last_accessed_at` 超过 30 天未命中 → archive（即使 expires_at 未到）
- 升级条件：`access_count >= 10 AND first_accessed_at <= (now - 14 days)` → `expires_at = NULL`
- 用户主动 pin → `expires_at = NULL`（直接变长期）

**短期默认存活期**：
- LLM 从对话中提取显式时间边界 → `valid_until`（写入 `expires_at`），如"今天" = 当日末尾
- 无时间边界 → 默认 `expires_at = now + 30 days`（与 last_accessed_at 30 天窗口对齐）

**为什么不永远保留所有记忆**：长期记忆可接受陈旧（检索质量自然过滤），短期记忆若永久保留会产生大量无效垃圾（如"今天要开会"）。

---

### 6. 检索门控：max_score < 0.5 跳过 access 更新

**决策**：向量检索返回结果后，若所有结果的最高余弦分 < 0.5，则：
- 仍返回结果（供 LLM 判断）
- **不**更新任何 `last_accessed_at` 和 `access_count`

**为什么**：随机闲聊（天气、笑话）会让每条短期记忆都"刷新"一次存活时间窗口，使 30 天窗口失效。0.5 阈值过滤低相关对话。

---

### 7. 向量存储：复用 VectorBackend 抽象

**决策**：facts 表不存 embedding BLOB。每条 active/superseded fact 写入 VectorBackend，namespace = `umem:{user_id}`。fact_id 作为向量 id。

**为什么**：VectorBackend 已有 Qdrant / in-memory 两实现，对 facts 无需再造；facts 表只存可查询的结构化字段，向量单独走后端。

---

### 8. 写入流水线：LLM 提取 → relation 归并 → classify_relation → 状态机提交

```
对话轮次 (user+assistant)
      │
      ▼
extract_facts(LLM)  →  list[RawFact]
      │
      ▼
resolve_relation     →  list[ResolvedFact]  (归并到词表 / 创建新词条)
      │
      ▼
classify_relations   →  list[ClassifiedFact]  (Equivalent/Contradict/NewSubsumed/Subsumes/Orthogonal)
      │                   并发，每条独立 LLM call
      ▼
commit_facts         →  事务：状态机提交，supersedes edges，向量 upsert
```

`classify_relation` 裁决表：

| 裁决 | 行为 |
|------|------|
| Equivalent | 跳过（已有等价事实存在）|
| Contradict | single→supersede；multi→supersede 最相似旧事实 |
| NewSubsumed | 跳过（旧事实更宽泛，新事实无增量） |
| Subsumes | 暂按 Orthogonal（延后处理） |
| Orthogonal | 插入新事实，不影响旧事实 |

---

## Risks / Trade-offs

**[R1] classify_relation 并发 LLM call 成本**
每轮对话可能提取 3-8 个 facts，每个独立 LLM call → 延迟叠加。
→ 缓解：classify 在后台异步运行（不阻塞对话回复）；批量提取时可合并 prompt 减少 call 数（后续优化）。

**[R2] relation_clusters 词表碎片化**
阈值 0.90 仍可能在早期积累大量长尾词条（relation 库小时向量空间稀疏）。
→ 缓解：预置 15+ 常见 relation；词表增长监控（超过 100 条时告警）；定期人工合并（非本次范围）。

**[R3] max_score 0.5 阈值误判**
低相关对话若恰好提到已知关键词（如 "Java coffee"），可能触发高相似度命中，错误刷新记忆存活时间。
→ 缓解：阈值可配置；后续可引入 LLM 二次相关性判断（非本次范围）。

**[R4] 现有记忆数据丢失**
旧 memory_items 数据无迁移路径，升级后用户从零积累。
→ 接受：旧数据质量本身不高（自由文本、重复）；从零开始比迁移错误数据更好。用户应在升级前告知。

**[R5] 30 天窗口对长期离线用户不友好**
用户 2 个月不用 agent，短期记忆全部消亡。
→ 接受：短期记忆本身设计上就是时间敏感的；高频使用的会在 30 天内升级为长期。

---

## Migration Plan

1. 新模块在 `src/fleetent/memory/` 中实现（facts_store.py、facts_pipeline.py、facts_lifecycle.py、facts_search.py、facts_models.py、facts_migrations.py）
2. `agent_state_migrations.py` 追加三张新表（facts / fact_edges / relation_clusters）的迁移 SQL，版本号递增
3. 旧 `store.py` / `extraction.py` / `operations.py` / `search.py` 标记 deprecated，public API 入口切换为新实现
4. `agent_app._init_agent_db_schema` boot 注入点无需修改（已走 forward-only 迁移，新表自动建立）
5. 无需 Alembic 迁移（facts 表在 agent_state.db，属嵌入式迁移 Y 体系）
6. 旧 memory_items 数据不迁移；升级后原表继续保留在 schema 中（不 DROP，防止读取报错）

**回滚**：降级 agent 版本即可，旧代码仍读 memory_items；facts 表在旧版本不存在不影响旧逻辑。

---

## Open Questions

- relation_clusters 初始词表是否需要本地化（中文 relation 名）？→ 暂时英文，待用户反馈
- classify_relation 是否需要 streaming 显示进度（用户可见）？→ 暂不需要，后台静默
- valid_until 时区处理：agent 从对话中如何感知用户时区？→ 暂时用 UTC，后续 agent profile 注入时区
