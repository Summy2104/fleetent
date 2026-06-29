## Context

`fleetent.knowledge_base` 当前在 ingest 与 delete 两处存在数据正确性缺陷（代码审计结论）：

- manual ingest（`ingest_text` / `ingest_parsed` → `_ingest_chunks` → `store.insert_document`）是纯 `INSERT`，无文档身份与去重，重复导入产生重复 document/chunk。
- `store.delete_document` 只清 `knowledge_chunks` / `knowledge_chunks_fts` 与向量，不触碰 `kb_entity_mentions` / `kb_relations` / `kb_entities`。

相关既有约束：
- 实体抽取是**显式触发**，ingest/sync 不自动抽取（"Explicit entity extraction runs"）。
- extraction 重跑后的孤儿实体清理 **deferred**（"Document-level replacement semantics"），针对"文档仍存在"的瞬时孤儿。
- `graph_search` 已在**读取层**按 `archived_at` 排除 archived 文档证据（"Graph search scope isolation"）。
- 表列名：`kb_entity_mentions.document_id`、`kb_entity_mentions.entity_id`；`kb_relations.evidence_document_id`、`kb_relations.source_entity_id`、`kb_relations.target_entity_id`；`kb_entities` 主键 `id`，UNIQUE `(tenant_id, kb_id, entity_type, normalized_name)`。

## Goals / Non-Goals

**Goals:**
- manual ingest 以 `(tenant_id, kb_id, source, filename)` 为身份，重复导入走覆盖（overwrite），库中始终一份最新。
- hard `delete(document_id)` 级联清理该文档的 mentions/relations，并 GC 真孤儿 entity；共享 entity 保留。
- 上述行为有 integration 级测试覆盖。

**Non-Goals:**
- 不改 `archive` / `archive_knowledge_base` 行为（archived 证据已由读取层排除，且需保留可恢复性）。
- 不改 extraction 触发策略（仍显式触发，不自动抽取）。
- 不改 connector 同步路径的身份（`source_path` / `content_hash`）与行为。
- 不引入版本化/历史保留；不引入 document-level ACL。
- 不改任何 public API 签名；不碰 platform / agent / node。

## Decisions

### D1. overwrite 以"delete-then-insert"实现，复用同一条删除级联
re-ingest 覆盖 = 先按身份找到旧 document 并走与 `delete()` **完全相同**的级联删除路径，再 insert 新版本。
- **为什么**：覆盖与删除的清理语义一致（chunks/fts/vector/mentions/relations/孤儿 GC），用一条实现避免两份清理逻辑漂移。
- **替代方案**：原地 UPDATE document + diff chunks。否决：chunk 数量/内容会变、向量 key 随 position 变，diff 复杂且易残留；delete-then-insert 简单且确定。

### D2. 文档身份 = `(tenant_id, kb_id, source, filename)`，在 store 层按身份查旧 document
ingest 前用该四元组查既有未归档 document；命中则覆盖。
- **为什么**：与 `source` 维度对齐——同一来源同名文件视为同一文档；不同 source 的同名文件是不同文档。
- **唯一约束**：是否给 `knowledge_documents` 加 `UNIQUE(tenant_id, kb_id, source, filename)`？**采用应用层按身份查 + 删旧**，先不加 DB 唯一约束。原因：历史数据可能已有重复行，加 UNIQUE 迁移会失败；应用层覆盖天然收敛到一份后，可在后续单独评估加约束。若实现中确需约束，走 `core/migrations.py` 嵌入式 forward-only 迁移（先去重再加约束），**不碰 Alembic**。

### D3. 孤儿 GC 的安全定义
删除某文档的 mentions/relations 后，一个 canonical entity 可被 GC 当且仅当：
- 在 `kb_entity_mentions` 中**零剩余 mention**（同 tenant/kb），**且**
- 不再作为 `kb_relations.source_entity_id` 或 `target_entity_id` 被任何剩余 relation 引用（同 tenant/kb）。
- **为什么两条都要**：entity 可能没有直接 mention 但仍是某条 relation 的端点；只看 mention 会误删仍被关系引用的 entity。

### D4. 孤儿 GC 只在 hard delete 触发，不在 extraction 重跑触发
保持与既有 "Document-level replacement semantics（orphan cleanup deferred）" 不矛盾。
- **原则区分**：extraction 重跑——文档仍在，孤儿是瞬时的、很快被新 mention 重新挂上，立即删反而抖动；hard delete——文档永久消失，孤儿是真孤儿。触发点不同，策略不同是合理的。

### D5. 事务边界
覆盖的"删旧 + 插新"、删除的"删 chunks/fts + 删 mentions/relations + GC entities"各自在**单个 store 事务**内完成（沿用 `store` 既有 `with transaction`），保证不出现半清理状态。vector_store 删除/upsert 在事务提交后调用（向量后端在 SQLite 事务之外），失败按既有 best-effort 语义记录。

## Risks / Trade-offs

- **[历史重复数据]** 现网若已存在同身份重复 document → 首次覆盖只删"查到的那一条"。**Mitigation**：按身份查询时若命中多行，删除全部命中行后再 insert（收敛到一份），并在测试覆盖"已存在重复→覆盖后只剩一份"。
- **[孤儿 GC 误删]** GC 条件写错可能删掉共享 entity。**Mitigation**：D3 双条件 + 专门的"共享 entity 存活"测试。
- **[vector 删除与 SQLite 事务非原子]** 进程在 SQLite 提交后、vector 删除前崩溃 → 残留向量。**Mitigation**：沿用既有 reindex public API 可重建；本 change 不扩大该既有边界，仅复用现有 delete 顺序。
- **[archive 与 delete 行为分叉]** 调用方需理解 archive 软删（读取层排除）vs delete 硬删（级联清理）。**Mitigation**：在 spec scenario 与代码 docstring 中明确两者区别。

## Migration Plan

- 纯行为修复，无 schema 变更（除非选择加唯一约束，见 D2，则走嵌入式 forward-only 迁移）。
- 部署即生效；旧的重复数据在下次同身份 re-ingest 时被覆盖收敛，旧的幽灵实体在对应文档下次 delete 时被清理（不做一次性回填，避免大范围扫描）。
- 回滚：还原代码即可；无破坏性 schema 动作。

## Open Questions

- 是否需要一次性 maintenance 任务清理现网存量幽灵实体/重复文档？倾向**否**（随自然 delete/re-ingest 收敛），如有需要另开 maintenance change。
