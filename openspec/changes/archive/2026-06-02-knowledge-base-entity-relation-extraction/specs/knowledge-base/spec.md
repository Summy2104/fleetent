## ADDED Requirements

### Requirement: Knowledge-base entity extraction schema
knowledge-base SHALL store entity extraction runs, canonical entities, entity mentions and relations in SQLite tables owned by the knowledge-base capability.

#### Scenario: Extraction tables exist after migration
- **WHEN** Alembic upgrade 到 head
- **THEN** 数据库包含 `kb_extraction_runs`
- **AND** 包含 `kb_entities`
- **AND** 包含 `kb_entity_mentions`
- **AND** 包含 `kb_relations`

#### Scenario: Entity dedupe key is scoped
- **WHEN** schema 创建 `kb_entities`
- **THEN** `(tenant_id, kb_id, entity_type, normalized_name)` 是唯一键
- **AND** 同名实体不会跨 KB 合并

### Requirement: Entity and relation type boundaries
knowledge-base SHALL use a fixed first-version set of entity and relation types for extraction output.

#### Scenario: Supported entity types
- **WHEN** extractor 输出 entity
- **THEN** entity_type 必须是 `person`、`team`、`organization`、`customer`、`project`、`system`、`document`、`concept` 或 `term`

#### Scenario: Supported relation types
- **WHEN** extractor 输出 relation
- **THEN** relation_type 必须是 `mentions`、`belongs_to`、`owns`、`depends_on`、`related_to`、`defines` 或 `conflicts_with`

#### Scenario: Unsupported extraction type fails fast
- **WHEN** extractor 输出未知 entity_type 或 relation_type
- **THEN** extraction validation fail fast
- **AND** 不写入 invalid row

### Requirement: Entity normalization and scoped upsert
knowledge-base SHALL normalize entity names and upsert canonical entities within a tenant + KB + type scope.

#### Scenario: Same normalized entity merges in one KB
- **WHEN** extraction 在同一 tenant + KB 中看到同类型 `Customer A` 和 `customer a`
- **THEN** 系统只保留一个 canonical entity

#### Scenario: Same normalized entity does not merge across KBs
- **WHEN** extraction 在不同 KB 中看到同类型同名 entity
- **THEN** 系统创建不同 canonical entities

### Requirement: Explicit entity extraction runs
knowledge-base SHALL run entity extraction only through an explicit extraction run, not as a default side effect of ingest or sync.

#### Scenario: Document extraction run
- **WHEN** 调用方显式对一个 document 运行 extraction
- **THEN** 系统只扫描该 document 的 chunks
- **AND** 写入 extraction run summary、entities、mentions 和 relations

#### Scenario: Knowledge-base extraction run
- **WHEN** 调用方显式对一个 KB 运行 extraction
- **THEN** 系统逐 document 扫描该 KB 的 chunks
- **AND** 单 document 失败不阻止后续 document
- **AND** run summary 记录 failed count

#### Scenario: Ingest does not auto-extract
- **WHEN** KB ingest 或 connector sync 写入 document / chunks
- **THEN** 系统不默认运行 entity extraction

### Requirement: Document-level replacement semantics
knowledge-base entity extraction SHALL replace active mentions and relations for a document only after that document extraction succeeds.

#### Scenario: Successful rerun replaces document evidence
- **WHEN** 对同一个 document 重新运行 extraction 且成功
- **THEN** 系统替换该 document 旧 mentions 和 relations
- **AND** 保留历史 `kb_extraction_runs` summary

#### Scenario: Failed rerun keeps previous evidence
- **WHEN** 对同一个 document 重新运行 extraction 失败
- **THEN** 系统不删除该 document 旧 active mentions 或 relations
- **AND** run summary 记录失败摘要

#### Scenario: Orphan entity cleanup is deferred
- **WHEN** document replacement 后某 entity 暂时没有 mentions
- **THEN** 本 change 不要求立即删除 entity
- **AND** orphan cleanup 留给后续 maintenance

### Requirement: Deterministic extractor
knowledge-base SHALL provide a deterministic extractor for tests and default local execution.

#### Scenario: Deterministic extractor produces entities
- **WHEN** deterministic extractor 处理固定 fixture
- **THEN** 它输出符合 schema 的 customer、project、system、team、concept 或 term entities

#### Scenario: Deterministic extractor produces relations
- **WHEN** deterministic extractor 处理固定 relation fixture
- **THEN** 它输出符合 schema 的 `depends_on`、`defines` 或 `conflicts_with` relations
- **AND** 每条 relation 包含 source chunk evidence

### Requirement: Extraction evidence
knowledge-base SHALL keep source evidence for entity mentions and relations.

#### Scenario: Entity mention keeps evidence
- **WHEN** extraction 写入 entity mention
- **THEN** mention 包含 document_id、chunk_id、text、confidence 和 extraction_run_id

#### Scenario: Relation keeps evidence
- **WHEN** extraction 写入 relation
- **THEN** relation 包含 source_entity_id、target_entity_id、evidence_document_id、evidence_chunk_id、evidence_text、confidence 和 extraction_run_id

#### Scenario: Evidence is summarized
- **WHEN** extraction 保存 evidence_text
- **THEN** evidence_text 不包含完整文档正文

### Requirement: Entity extraction public API and CLI
knowledge-base SHALL expose explicit entity extraction through public API and admin CLI.

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 entity extraction models 和 `run_entity_extraction`
- **THEN** 导入成功

#### Scenario: Admin CLI triggers extraction
- **WHEN** operator 运行 `fleetent admin kb extract-entities --kb-id <kb_id>`
- **THEN** CLI 调用 KB-level explicit extraction run
- **AND** 输出脱敏 run summary

#### Scenario: Admin CLI supports document scope
- **WHEN** operator 运行 `fleetent admin kb extract-entities --kb-id <kb_id> --document-id <document_id>`
- **THEN** CLI 调用 document-level explicit extraction run
- **AND** 输出脱敏 run summary

### Requirement: Optional LLM extractor smoke
knowledge-base MAY provide a real LLM extractor smoke path, but it SHALL be explicitly opt-in and skipped by default.

#### Scenario: Real LLM extraction smoke is skipped by default
- **WHEN** 未设置 `FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1`
- **THEN** real LLM extraction smoke 被 skip

#### Scenario: Real LLM extraction requires provider config
- **WHEN** 设置 opt-in 但 provider config 或 credential 缺失
- **THEN** real LLM extraction smoke 被 skip
- **AND** 不影响默认测试

### Requirement: Entity extraction exclusions
knowledge-base entity extraction SHALL NOT implement graph search, automatic sync integration, scheduler, entity merge review or document ACL.

#### Scenario: Graph search remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** `search()` 和 hybrid ranking 不因 entities / relations 改变
- **AND** 不新增 graph traversal search

#### Scenario: Scheduler remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** extraction 不自动进入 scheduler 或 worker
- **AND** 只通过 explicit run 触发
