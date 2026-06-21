# Design

## 设计目标

第一版 entity / relation extraction 只负责三件事：

1. 从已有 KB chunks 生成实体、提及和关系。
2. 把结果稳定落到 SQLite 表里，并保留 source evidence。
3. 支持显式重跑和 deterministic tests，为 graph search 做前置。

它不进入默认 KB sync，不改变检索结果，不引入自动后台任务。

## Entity Types

第一版 entity types 固定为：

```text
person
team
organization
customer
project
system
document
concept
term
```

说明：

- `customer` 独立于 `organization`，用于表达企业服务对象。
- 不在第一版细分 vendor、partner、competitor。
- 不做行业专属 schema；后续如需要可通过独立 spec 扩展。

## Relation Types

第一版 relation types 固定为：

```text
mentions
belongs_to
owns
depends_on
related_to
defines
conflicts_with
```

说明：

- 暂不加入 `serves`，避免第一版过早业务化。
- `related_to` 是兜底 relation，但 extractor 应克制使用，避免生成低质量泛关系。

## Normalization and Deduplication

entity 唯一键：

```text
tenant_id + kb_id + entity_type + normalized_name
```

规范化建议：

- trim whitespace。
- casefold。
- 合并连续空白。
- 保留原始 display name 作为 `name`。

不同 KB 不合并 entity。这样可以避免跨 KB 的误合并，也符合现有 KB scope / agent binding 边界。

第一版不做 merge / split review lifecycle。误合并后续通过 maintenance 或 graph quality spec 处理。

## Tables

### `kb_extraction_runs`

记录每次 extraction run 的 summary。

字段建议：

```text
id
tenant_id
kb_id
document_id nullable
extractor
status
started_at
finished_at
documents_scanned
chunks_scanned
entities_upserted
mentions_written
relations_written
failed_count
error_summary
metadata_json
```

### `kb_entities`

canonical entity 表。

字段建议：

```text
id
tenant_id
kb_id
entity_type
name
normalized_name
metadata_json
created_at
updated_at
```

唯一约束：

```text
(tenant_id, kb_id, entity_type, normalized_name)
```

### `kb_entity_mentions`

entity 在 chunk 中的 evidence。

字段建议：

```text
id
entity_id
tenant_id
kb_id
document_id
chunk_id
text
confidence
extraction_run_id
created_at
```

### `kb_relations`

entity 间关系。

字段建议：

```text
id
tenant_id
kb_id
relation_type
source_entity_id
target_entity_id
evidence_document_id
evidence_chunk_id
evidence_text
confidence
extraction_run_id
created_at
```

## Write Strategy

第一版采用 document 级 replace：

- 按 document 重跑时，新 run 成功后替换该 document 的 active mentions / relations。
- 按 KB 全量跑时，逐 document 执行 document replace。
- `kb_extraction_runs` 保留历史 run summary。
- 旧 active mentions / relations 不保留；实现可直接删除旧 rows。
- `kb_entities` 按 normalized key upsert，不因某次 document replace 自动删除 orphan entities。
- orphan entity cleanup 留给后续 maintenance spec。

替换时机：

- 推荐先在事务中生成 / upsert entities，再删除该 document 旧 mentions / relations，再写入新 mentions / relations，最后标记 run succeeded。
- 如果 run 失败，不应删除该 document 已有 active mentions / relations。

## Trigger Model

第一版 extraction 是显式 run，不随 sync / ingest 默认执行。

支持：

```python
run_entity_extraction(tenant_id: str, kb_id: str, document_id: str | None = None, extractor: str = "deterministic")
```

CLI：

```bash
fleetent admin kb extract-entities --kb-id engineering
fleetent admin kb extract-entities --kb-id engineering --document-id doc-123
```

后续 Admin API、scheduler 或 worker 可以触发同一 public API，但本 change 不实现后台运行。

## Deterministic Extractor

默认 extractor 用于测试和 CI，不追求真实 NLP 质量。

它应能稳定解析类似 fixture：

```text
Customer: Acme
Project: Atlas
System: Billing API
Team: Platform
Depends on: Data Warehouse
Conflict: Legacy Billing conflicts with Billing API
```

输出包括：

- extracted entities
- extracted mentions with chunk evidence
- extracted relations with source / target entities and evidence chunk

## LLM Extractor Boundary

第一版只预留接口和 opt-in smoke guard：

- 默认不调用真实 LLM。
- 默认 CI 不跑真实 LLM。
- 真实 smoke 需要显式环境变量，例如 `FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1`。
- 缺少 provider config 时 skip，而不是 fail。

LLM extractor 不改变 write strategy；输出仍需经过相同 schema validation 和 upsert path。

## Evidence

mentions / relations 必须保存 evidence：

- `document_id`
- `chunk_id`
- evidence text 或 mention text summary
- confidence
- extraction_run_id

证据文本应短小、脱敏边界清晰，不保存完整文档正文。

## Failure Handling

- 单 document extraction 失败不影响其他 documents。
- run summary 记录 failed count 和 sanitized error summary。
- document 级 run 失败时不删除旧 active mentions / relations。
- unsupported extractor fail fast。

## Testing Strategy

Unit tests：

- entity type / relation type validation。
- name normalization。
- deterministic extractor。
- upsert dedupe key。
- document replace 不删除旧 results until success。

Integration tests：

- Alembic migration creates tables / unique constraints。
- run extraction by document writes entities / mentions / relations。
- rerun document replaces mentions / relations and preserves run summaries。
- full KB extraction scans multiple documents and isolates per-document failure。

Evaluation / smoke：

- deterministic fixture checks expected entities and forbidden relations。
- real LLM smoke default skip without opt-in。

## Relationship to Graph Search

本 change 不实现 graph traversal 或 graph retrieval。

`knowledge-base-graph-search` 后续将基于：

- `kb_entities`
- `kb_entity_mentions`
- `kb_relations`
- evidence chunk ids

实现关系展开和 graph retrieval evaluation。
