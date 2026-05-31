## Overview

本 change 是 knowledge-base 的前置规划，不实现运行时功能。它的目标是避免在一个 spec 中同时处理
旧项目迁移、数据模型、parser、connector、sync、search、权限和 long-term-ctx 集成。

## Source Project

迁移评估对象：

```text
../knowledge-bridge
```

重点阅读：

- `README.md`
- `ARCHITECTURE.md`
- `docs/DESIGN.md`
- `docs/ROADMAP.md`
- `knowledge_bridge/core/`
- `knowledge_bridge/parsers/`
- `knowledge_bridge/connectors/`
- `knowledge_bridge/sync/`
- `knowledge_bridge/pipeline/`
- `knowledge_bridge/retrieval/`
- `knowledge_bridge/metadata/`
- `knowledge_bridge/audit/`

## Required Output

本 change 应产出一份迁移计划文档，建议路径：

```text
docs/knowledge-bridge-migration-plan.md
```

文档必须包含：

1. `knowledge-bridge` 能力盘点。
2. 与 fleetent 约束的差异分析。
3. 可直接迁移 / 需重写 / 暂缓 / 不迁移分类表。
4. 推荐的 fleetent knowledge-base specs 拆分。
5. 第一批 specs 的依赖顺序和风险。
6. 不引入的依赖清单与原因。

## Migration Categories

### 可直接迁移

原则：代码不依赖 LlamaIndex、LanceDB、OpenAI Embeddings、Poetry runtime home 或服务进程模型，
且只需轻量适配 fleetent dataclass / config。

候选：

- Markdown / text parser 逻辑。
- HTML 清洗逻辑。
- 部分 PDF / DOCX / PPTX / XLSX parser 逻辑（需依赖评估）。
- 本地目录 connector 的遍历与变更检测逻辑。
- Confluence 分页、限速和 429 backoff 逻辑。
- Google Drive 分页、变更 token 和限速逻辑。
- sync planner 的动作模型。
- retrieval audit 的“只存摘要，不存 raw query / chunk content”理念。

### 可参考但需重写

原则：业务思想有价值，但实现绑定不适合 fleetent。

候选：

- Vector store：LanceDB → fleetent `vector_store`。
- Embedding：OpenAI Embeddings → 自托管 / deterministic / sidecar。
- Chunker：TextNode / LlamaIndex 类型 → fleetent `KnowledgeChunk` / section dataclass。
- Retrieval engine：LanceDB hybrid/FTS → fleetent vector_store + SQLite FTS5 / BM25。
- Query scope：agent_id scope → fleetent tenant_id + kb_id + agent binding。
- REST API/admin UI：旧服务边界 → fleetent platform/admin API。

### 暂缓迁移

原则：能力有价值，但不是 knowledge-base MVP 的基础依赖。

候选：

- Google Drive webhook。
- MCP proxy。
- image ingestion / VLM。
- spreadsheet LLM interpreter。
- reranker。
- multi-worker sync runtime。
- production systemd deployment scripts。

### 不迁移

原则：违反 fleetent 约束，或由 fleetent 已有模块替代。

候选：

- LlamaIndex dependency。
- LanceDB as direct storage dependency。
- OpenAI Embeddings as default embedding。
- Poetry-specific runtime assumptions。
- standalone REST service as primary boundary。

## Recommended Spec Split

迁移计划应至少评估并排序这些后续 specs：

1. `knowledge-base-core`
   - tenant_id + kb_id
   - documents / chunks tables
   - manual text / markdown ingest
   - deterministic chunking
   - vector_store indexing
   - search returns `KnowledgeChunk`

2. `knowledge-base-parsers`
   - 迁移 markdown / html / pdf / docx / xlsx / pptx parser
   - 输出 fleetent 内部 plain text / section dataclass
   - 不接数据源同步

3. `knowledge-base-connectors-local`
   - 本地目录 connector
   - 手动 sync run
   - 变更检测

4. `knowledge-base-connectors-confluence`
   - Confluence connector
   - 分页、限速、增量同步

5. `knowledge-base-connectors-google-drive`
   - Google Drive connector
   - OAuth / service account / change token

6. `knowledge-base-hybrid-search`
   - SQLite FTS5 / BM25
   - RRF
   - 中文分词策略

7. `knowledge-base-graph-search`
   - entity / relation extraction
   - graph_search

8. `knowledge-base-sync-planner`
   - SKIP / UPSERT_METADATA_ONLY / REEMBED / RECHUNK_LOCAL / REFETCH_AND_REINDEX / DELETE_LOCAL
   - 后台任务与幂等执行

## Acceptance Criteria

完成本 change 后，团队应能回答：

- 第一个可执行 KB implementation spec 是什么？
- 哪些 `knowledge-bridge` 文件可以作为迁移参考？
- 哪些依赖不能进入 fleetent？
- 哪些能力必须后置？
- 每个后续 spec 的边界和依赖是什么？

## Validation

本 change 不运行代码测试。需要验证：

- `openspec validate 2026-05-31-knowledge-bridge-migration-plan`
- migration plan 文档无 TBD / TODO。
- capability 文档链接到 migration plan。
