## Context

facts 表存储结构化三元组 `(subject, relation, object)`，通过向量检索按语义相关性召回注入 prompt。当前所有 facts 走同一套召回路径，但行为指令类 fact（`response_style`、`never_do` 等）的语义与用户 query 无关，靠向量相似度无法稳定命中，导致 agent 随机遗忘用户设定的行为规则。

现有代码关键路径：
- `memory/facts_store.py`：facts CRUD + vector upsert，已有 `list_active_facts()`（纯 SQL，无向量）
- `memory/facts_search.py`：`search_facts()` 向量检索主路径
- `memory/facts_pipeline.py`：LLM 提取 → `ExtractedFact` dataclass → 写库
- `long_term_ctx/__init__.py`：`build_context()` 并发拉三路（memory / knowledge / agent_memory）→ 合并注入

## Goals / Non-Goals

**Goals:**
- 行为指令类 facts 每轮无条件注入，不漏召
- always facts 数量可控，不无限增长
- 未知 relation 默认安全（hard），不被误淘汰
- 现有 situational 召回行为不变

**Non-Goals:**
- 场景感知注入（tool 调用前按场景动态注入）——后续迭代
- user_instructions（user.md 静态指令）与 always facts 的合并展示
- always facts 的用户管理 UI

## Decisions

### D1：scope 字段而非 relation 白名单

**决策**：facts 表加 `scope TEXT NOT NULL DEFAULT 'situational'`，提取时 LLM 显式输出 scope。

**备选**：按 relation 名白名单自动判断。

**理由**：relation 名由 LLM 自由生成，无枚举约束，白名单永远不完整（`reply_style` vs `response_style`）。显式字段让 scope 成为一个明确的提取输出维度，LLM 只需回答"这条指令是否每次都应该生效"，比猜 relation 名更可靠。

### D2：soft 白名单 + 未知默认 hard

**决策**：
```
SOFT_RELATIONS = {"response_style", "tone", "format", "language", "output_format"}
# 不在白名单里的 relation → hard（不参与淘汰）
```

**理由**：用户提到的核心安全问题——LFU/LRU 会优先淘汰命中频率低的 guardrail（`never deploy to prod without confirm` 可能几个月才触发一次）。soft 白名单 + 未知默认 hard 确保任何 LLM 造出的新 relation 变体都不会被误淘汰。降级为 situational 的动作也去掉，超限直接 retract（对 directive 而言降级 ≈ 静默禁用）。

### D3：always facts 独立 section，在 situational 之前注入

**决策**：`build_context()` 在并发检索之前先同步查 `always` facts，渲染为独立 section `[Behavioral directives — 始终生效的行为规则]`，置于 `[Long-term memory]` 之前。

**备选**：注入到 system prompt 稳定前缀（`[用户指令]` 区域）。

**理由**：注入到稳定前缀会破坏 prefix cache（always facts 内容随用户设置变化）。独立 section 保持动态区，语义清晰（模型能区分"规则"和"事实"），实现最小——`list_pinned_facts()` 纯 SQL，不走向量。

### D4：soft 上限超限时 retract 最旧条目

**决策**：写入新 `always` fact 时，若 soft 池已满（≥15 条），按 `updated_at ASC` 取最旧一条执行 retract，再写入新条目。在 `facts_store.upsert_fact()` 写入路径中内联执行，保持原子性。

**理由**：soft 类（tone/format 等）是用户的偏好调整，新的覆盖旧的语义合理。retract 而非降级，语义清晰，不留僵尸 facts。

## Risks / Trade-offs

- **[风险] 提取时 LLM 误判 scope**：把 situational fact 标为 always → 轻微浪费 token 预算；把 always 标为 situational → 问题依旧。  
  → 缓解：提取 prompt 加明确示例，`always` 门槛写严（"每次对话都必须执行"）；提取日志记录 scope 字段供调试。

- **[风险] 回填 migration 误判现有 facts**：现有 facts 按 relation 名回填，可能有遗漏。  
  → 缓解：回填只设 known soft/hard 清单，其余保持 `situational`（而非猜测为 always），保守方向。

- **[Trade-off] always facts 不走向量，access_count 不更新**：现有 upgrade（短期→长期）逻辑依赖 access_count。  
  → always facts 绕过 `search_facts()`，access_count 不增长，不会触发 upgrade——这是期望行为（always facts 的生命周期由 scope + soft 淘汰管理，不需要 access_count 语义）。

## Migration Plan

1. `agent_state_migrations.py` 新增 migration：
   - `ALTER TABLE facts ADD COLUMN scope TEXT NOT NULL DEFAULT 'situational'`
   - 回填：`UPDATE facts SET scope='always' WHERE relation IN ('response_style','tone','format','language','output_format','never_do','always_do','security','approval_required') AND status='active'`
2. 无 rollback 需求（新列有 DEFAULT，旧代码读不到新列但不崩溃）

## Open Questions

- soft 上限 15 条是否合适？可在 `agent.yaml` `long_term_ctx` block 加配置项，后续迭代。
- 是否需要 `recall_memory` 工具也展示 always facts？当前工具展示 `list_active_facts`，always facts 已包含在内，无需额外改动。
