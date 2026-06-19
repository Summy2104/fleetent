# knowledge-base-entity-relation-extraction

## Why

当前 knowledge-base 已经具备 ingest、chunking、hybrid retrieval、connector sync 和 reindex 能力，但尚未保存
文档中的实体和关系。后续 `knowledge-base-graph-search`、KB reflection reports 和 query planner 都需要一个稳定的
entities / relations source of truth。

本 change 先建立 entity / relation extraction 的数据模型和显式执行链路，不把它接入默认 sync，也不影响现有
search ranking。目标是为后续 graph search 提供可回归、可替换、可审计的图数据基础。

## What Changes

- 新增 Alembic 表：
  - `kb_extraction_runs`
  - `kb_entities`
  - `kb_entity_mentions`
  - `kb_relations`
- 定义第一版 entity types：
  - `person`
  - `team`
  - `organization`
  - `customer`
  - `project`
  - `system`
  - `document`
  - `concept`
  - `term`
- 定义第一版 relation types：
  - `mentions`
  - `belongs_to`
  - `owns`
  - `depends_on`
  - `related_to`
  - `defines`
  - `conflicts_with`
- entity 去重 key 为 `tenant_id + kb_id + entity_type + normalized_name`。
- 新增显式 extraction run API / CLI，支持按 KB 或按 document 执行。
- extraction 不随 KB sync / ingest 默认执行。
- 按 document 重跑时替换该 document 的 active mentions / relations；保留 extraction run summary。
- 默认 deterministic extractor，用于测试和 CI。
- 预留 LLM extractor 接口和 opt-in smoke guard，但默认不调用真实 LLM。

## 模块边界影响

- owning package：`intelligence.knowledge_base`。
- public API surface：
  - entity / relation dataclasses。
  - extraction run service，例如 `run_entity_extraction(tenant_id, kb_id, document_id=None, extractor=\"deterministic\")`。
  - admin CLI，例如 `fleetent admin kb extract-entities --kb-id ... [--document-id ...]`。
- owned tables：新增 knowledge-base-owned `kb_extraction_runs`、`kb_entities`、`kb_entity_mentions`、`kb_relations`。
- config namespace：无新增默认 runtime config；真实 LLM smoke 使用显式环境变量 opt-in。
- cross-module dependencies：
  - 读取 knowledge-base chunks。
  - 可选 LLM extractor 通过 model router / provider boundary，但不进入默认测试。
  - 不依赖 vector store、long-term context 或 graph search。
- migration / shim plan：新增 Alembic migration；无 legacy shim。

## 非目标

- 不实现 graph search。
- 不改变 `search()`、hybrid ranking 或 long-term context provider。
- 不做 entity merge review lifecycle。
- 不做 orphan entity cleanup。
- 不做 scheduler / worker。
- 不随 sync / ingest 自动执行。
- 不做 document-level ACL。
- 不做多语言 NLP 质量优化或第三方 NER 库。
- 不默认调用真实 LLM。
