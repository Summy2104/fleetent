# knowledge-bridge 迁移计划

本计划对应 OpenSpec change `2026-05-31-knowledge-bridge-migration-plan`。它只做迁移评估和后续 specs 拆分，不实现 fleetent knowledge-base 运行时代码。

明确不做：

- 不迁移 parser / connector 代码。
- 不实现 knowledge-base tables。
- 不实现 ingest/search。
- 不引入 LlamaIndex。
- 不引入 LanceDB。
- 不引入 OpenAI Embeddings。
- 不引入 docling 等新运行时依赖。

## 目标和边界

`knowledge-bridge` 已覆盖企业知识库的多数工程经验：数据源连接、文档解析、结构化分块、增量同步、混合检索、query scope、审计和运维入口。fleetent 不能直接依赖该项目，因为 fleetent 的模块边界、数据库生命周期、向量存储边界、模型路由和 on-premises 约束不同。

迁移策略是先继承设计资产，再按 fleetent specs 渐进实现。第一批实现只应选择最小闭环，避免在一个 spec 中同时处理 parser、connector、sync、hybrid search、graph search 和 long-term-ctx 集成。

## knowledge-bridge 能力盘点

| 模块 | 已有能力 | 关键依赖 / 绑定 | fleetent 适配判断 |
| --- | --- | --- | --- |
| `core` | `DocumentInfo`、`RawDocument`、`ParsedBlock`、`ParsedDocument`、`Parser`、`Chunker`、`MetadataStore`、`KnowledgeBase`、`QueryAgent` 等抽象 | dataclass 为主，但部分接口面向 LlamaIndex、agent_id scope 和独立服务配置 | 类型设计可参考；public API 需要改为 `tenant_id + kb_id` 和 fleetent dataclass |
| `parsers` | text、Markdown、HTML、PDF、DOCX、PPTX、CSV/XLSX、Google Docs、Google Sheets、image；统一 section-first 输出 | `beautifulsoup4`、`pandas`、`pypdf`、`pymupdf`、`python-docx`、`openpyxl`、`python-pptx`、可选 VLM/docling | text/Markdown/HTML 和 section 化最适合先迁移思想；Office/PDF 需逐项依赖评估；image/docling 后置 |
| `connectors` | local file、Confluence、Google Drive；分页、限速、429 backoff、Drive change token、scope signature、移动/删除判定 | 继承 LlamaIndex `BaseReader`，输出 LlamaIndex `Document`；依赖 atlassian / Google SDK | 连接器算法可参考；接口和输出必须重写为 fleetent `DataSource` |
| `sync` | `SyncIntent`、`ChangeCandidate`、`PlannedAction`、`ExecutionResult`；动作模型覆盖 SKIP、metadata-only、reembed、rechunk、refetch、delete | 与 metadata store、index version、projection hash、embedding 配置漂移联动 | 动作模型价值高；应在 core 可用后独立 spec 重写 |
| `pipeline` | Connector -> Parser -> Chunker -> Embedder -> VectorStore + MetadataStore 编排；支持并行处理、失败状态、删除确认 | 强绑定 LlamaIndex `Document` / `KBNodeParser`、OpenAI embedder、LanceDB、runtime home | 不迁移实现；只参考幂等、删除确认、index state 思路 |
| `retrieval` | naive、BM25、hybrid；RRF 融合；query planner/translator；metadata filters；可选 reranker | LlamaIndex `NodeWithScore`、vector store 原生 LanceDB text/hybrid search、OpenAI-compatible LLM | 检索策略可参考；实现必须基于 fleetent `vector_store` + SQLite FTS5 / BM25 |
| `metadata` | SQLite 元数据、knowledge bases、query agent bindings、source sync state、index/reindex/admin job state | 自行 `_init_db()` / 补列迁移；SQL 使用 `?`；独立 meta.db | 不直接迁移；fleetent 要走 Alembic 和统一 DB runtime/store 边界 |
| `audit` | SQLite retrieval audit，短期保留 request/result 摘要，按时间裁剪 | 代码当前会保存 raw query，且自行建表、`?` 占位符 | 只迁移“短保留、有限结果、避免 chunk content”理念；fleetent 版本不应默认保存 raw query |

## fleetent 约束差异分析

| 主题 | knowledge-bridge | fleetent 约束 | 处理方式 |
| --- | --- | --- | --- |
| 架构边界 | 独立 REST / CLI / MCP proxy 服务 | modular monolith；knowledge-base 属于 `intelligence.knowledge_base`，由 platform/admin/long_term_ctx 调用 | 不引入 standalone REST service boundary；后续用 fleetent public API 和现有 HTTP/admin 边界 |
| AI 框架 | 依赖 `llama-index-core` 类型、reader、node | 禁止 LlamaIndex / LangChain / LangGraph | 所有 `BaseReader`、`Document`、`TextNode`、`NodeWithScore` 相关代码重写 |
| 向量存储 | LanceDB 直接存储向量与 FTS 字段 | 使用 fleetent `vector_store` 边界，不能让业务层直连 LanceDB | vector search 走 public `vector_store` API；词法检索先用 SQLite FTS5 / BM25 |
| Embedding | OpenAI SDK 和 OpenAI-compatible embeddings | 禁止云托管 embeddings 作为默认能力 | 使用 fleetent `embedding.*` HTTP provider 边界接入自托管模型服务；默认 deterministic provider 仅用于本地和测试 |
| 数据库 | metadata store 自建表、补列迁移、`sqlite3.connect`、`?` 参数 | Alembic 管 schema；store SQL 用 named parameters；业务层不扩散 sqlite3 | 不迁移 store 实现；只迁移字段语义和状态机 |
| 知识库身份 | `agent_id -> kb_ids` query scope | `tenant_id + kb_id`，agent 绑定一个或多个 kb | query scope 重写为 tenant-aware binding；默认 tenant 为 `default` |
| 数据主权 | 可配置 OpenAI-compatible、Google Drive OAuth、VLM | on-premises 优先，禁止云托管专有服务破坏数据主权 | 外部 SaaS 连接器可作为可选数据源；模型能力默认 self-host |
| 依赖管理 | Poetry、固定 `~/.knowledge-bridge` runtime home | fleetent 使用 uv、项目配置和 data 隔离 | 不迁移 Poetry/runtime home 假设 |

## 迁移分类

### 可直接迁移清单

这里的“直接迁移”指后续 specs 可以复制小块无框架绑定的算法并改名适配 fleetent 类型；本 change 不复制代码。

| 能力 | 来源 | 迁移方式 | 注意事项 |
| --- | --- | --- | --- |
| text parser 的空内容过滤和 body section 输出 | `parsers/text.py` | 改为 fleetent `ParsedSection` / plain text 输出 | 不带外部依赖，适合作为 parser spec 的第一项 |
| Markdown 基础块识别、code fence 保护、HTML table 归一 | `parsers/markdown.py` | 复制算法，替换 `ParsedBlock` 类型 | `pandas.to_markdown` 依赖需评估；可先用本地 table renderer |
| HTML 清洗、Confluence storage macro 展开、表格转文本 | `parsers/html.py` | 迁移清洗规则和表格策略 | 保留 `beautifulsoup4` 是否进入依赖由 parser spec 决定 |
| section-first 归并、目录过滤、空 section 过滤 | `parsers/_sectionize.py` | 迁移为 fleetent parser 内部 helper | 这是后续 deterministic chunking 的重要输入 |
| 本地目录遍历、后缀到 content type 映射、mtime 变更检测 | `connectors/local_file.py` | 重写接口，复用遍历规则 | 去掉 LlamaIndex `BaseReader` 和 `load_data()` |
| Confluence 限速、429 backoff、分页、ancestor/path 元数据 | `connectors/confluence.py` | 迁移算法到 fleetent connector | 输出 `DocumentRef` / raw bytes；认证配置走 `knowledge_base.sources.confluence.*` |
| Google Drive folder/file scope、change token、删除二次确认、path 元数据 | `connectors/google_drive.py` | 迁移算法到 fleetent connector | OAuth token 存储、tenant 隔离和 webhook 后置 |
| sync planner 动作模型 | `sync/models.py`、`sync/planner.py` | 迁移 dataclass 语义和决策表 | action 名称可保留；store 和 execution 需 fleetent 化 |
| 中文 lexical tokenizer 思路 | `retrieval/lexical.py` | 迁移 jieba + CJK bigram 思路 | SQLite FTS5 下字段和 tokenizer 策略需重新验证 |

### 可参考但需重写清单

| 能力 | 为什么有价值 | 为什么必须重写 | 推荐落点 |
| --- | --- | --- | --- |
| vector store 写入和搜索 | 已验证 chunk/entity key、metadata、hybrid search 需要的字段 | LanceDB direct dependency 违反 fleetent `vector_store` 边界 | `knowledge-base-core` 使用 existing `vector_store` public API |
| embedding 调用 | 区分 query embedding 和 document embedding，支持模型维度漂移 | OpenAI Embeddings 不能作为默认能力 | 通过已定义的 HTTP embedding provider 接入 self-host embedding sidecar；KB spec 只消费 provider 边界 |
| chunker / node parser | section-aware chunking 和 parent expansion 思路有用 | `TextNode`、`KBNodeParser`、LlamaIndex metadata 绑定 | `knowledge-base-core` 定义 deterministic chunk dataclass |
| retrieval engine | naive/BM25/hybrid/RRF、candidate_k、metadata filters 有参考价值 | `NodeWithScore`、LanceDB FTS/hybrid、OpenAI query planner 绑定 | `knowledge-base-hybrid-search` 重写 search orchestration |
| query scope | 一个 agent 绑定多个 KB 的产品模型有价值 | fleetent 以 `tenant_id + kb_id` 和 agent binding 为隔离单位 | `knowledge-base-core` 先定义 namespace 和 binding 约定 |
| metadata store | 字段覆盖 source sync state、index state、admin jobs | 自建表、补列迁移、`sqlite3.connect`、`?` 占位符不符合约束 | 拆到 Alembic + store package |
| retrieval audit | 短保留、有限结果、结果摘要利于调试 | 当前保存 raw query，且自建 SQLite lifecycle | `knowledge-base-retrieval-audit` 后置，默认 query hash/redaction |
| REST/admin UI | operator workflow 清晰 | fleetent 已有 FastAPI/admin 边界 | 后续 platform/admin spec 集成 |

### 暂缓迁移清单

| 能力 | 暂缓原因 | 前置条件 |
| --- | --- | --- |
| Google Drive webhook | MVP 可用手动/定时 sync；webhook 涉及公网 callback、安全校验和多租户 token | Google Drive connector、sync planner、admin job state 稳定 |
| MCP proxy | fleetent 已有 MCP 工具命名和 agent runtime；KB 先通过 long_term_ctx 调用 | search API 和 long_term_ctx 集成完成 |
| image ingestion / VLM | 需要 VLM、图片安全策略和成本控制 | text/PDF/Office parser 稳定，自托管 VLM 路径明确 |
| spreadsheet LLM interpreter | LLM 解释表格会引入模型成本和稳定性问题 | 基础 xlsx/google sheet 结构化解析完成 |
| reranker | MVP 先验证 vector + BM25 + RRF | hybrid search 指标和审计可观测后 |
| multi-worker sync runtime | 并发写入、幂等锁和失败恢复复杂 | 单 worker sync executor 和 job state 完成 |
| production systemd/deploy scripts | fleetent 部署体系独立 | fleetent 运维部署 spec 另行处理 |
| query planner / translator | 依赖 LLM 调用，容易扩大 search scope | 基础 hybrid search 与 model routing 策略完成 |

### 不迁移清单与原因

| 能力 / 依赖 | 结论 | 原因 |
| --- | --- | --- |
| LlamaIndex dependency | 不迁移 | fleetent 明确禁止 AI 框架依赖；相关类型会污染 public API |
| LanceDB direct dependency | 不迁移 | fleetent 业务层必须走 `vector_store`，不能直接绑定 LanceDB |
| OpenAI Embeddings default | 不迁移 | 默认能力必须支持 on-premises / self-host；云托管 embeddings 只能作为明确可选适配 |
| docling runtime dependency | 不迁移到第一批 specs | 依赖重、运行时复杂；本 change 明确不引入 |
| standalone REST service boundary | 不迁移 | fleetent 已有 FastAPI/server/admin 边界，KB 应作为内部 package 暴露 API |
| Poetry/runtime home 假设 | 不迁移 | fleetent 使用 uv 和项目配置；测试需要 tmp_path/fixture 隔离 |
| metadata store 建表/补列模式 | 不迁移 | fleetent schema lifecycle 由 Alembic 管理 |
| `?` SQL 占位符风格 | 不迁移 | fleetent store 层使用 named parameters |
| raw query 默认审计存储 | 不迁移 | 可能保存敏感问题；fleetent 审计默认应 hash/redact query，不存 chunk content |

## 后续 fleetent KB specs 拆分和推荐顺序

| 顺序 | spec | owning package | 最小范围 | 依赖 | 不包含 |
| --- | --- | --- | --- | --- | --- |
| 1 | `knowledge-base-core` | `intelligence.knowledge_base` | `tenant_id + kb_id`、documents/chunks Alembic 表、manual text/markdown ingest、deterministic chunking、vector_store indexing、`search()` 返回 `KnowledgeChunk` | fleetent DB runtime/store、`vector_store` public API、config namespace | parser 迁移、connector、hybrid BM25、graph search、sync planner |
| 2 | `knowledge-base-parsers-basic` | `intelligence.knowledge_base.parsers` | text、Markdown、HTML parser；section-first 输出；不接外部数据源 | core ingest 接受 parsed sections | PDF/DOCX/PPTX/XLSX、docling、image/VLM |
| 3 | `knowledge-base-connectors-local` | `intelligence.knowledge_base.connectors` | local directory `DataSource`、manual sync run、mtime/hash 变更检测 | core ingest、basic parsers | Confluence/Drive、后台调度器、多 worker |
| 4 | `knowledge-base-hybrid-search` | `intelligence.knowledge_base.retrieval` | SQLite FTS5 / BM25、中文 lexical strategy、RRF 融合、`limit`/namespace 过滤 | core chunks table、vector_store search | reranker、query planner、graph search |
| 5 | `knowledge-base-sync-planner` | `intelligence.knowledge_base.sync` | sync action model、plan/run separation、idempotent execution 状态 | core store、local connector | webhooks、多 worker、跨源调度 |
| 6 | `knowledge-base-connectors-confluence` | `intelligence.knowledge_base.connectors` | Confluence Server/DC list/fetch、分页、限速、增量 token、scope rules | sync planner、basic parsers | Cloud-only behavior、ACL enforcement |
| 7 | `knowledge-base-connectors-google-drive` | `intelligence.knowledge_base.connectors` | Drive file/folder scope、OAuth/service account、change token、Google Docs/Sheets export | sync planner、parser specs、token store decision | webhook、shared-drive edge hardening、spreadsheet LLM interpreter |
| 8 | `knowledge-base-graph-search` | `intelligence.knowledge_base.graph` | entities/relations Alembic 表、`kb_extraction` task、entity vector indexing、`graph_search()` | core ingest/search、model_router task routing | ontology UI、GraphRAG framework、cross-tenant graph |
| 9 | `knowledge-base-retrieval-audit` | `observability` + `intelligence.knowledge_base` public events | retrieval summary, latency, result ids, score, query hash/redaction, retention | search API stable | raw query/chunk content storage by default |

推荐顺序把 `knowledge-base-hybrid-search` 放在 Confluence/Drive 之前，是为了让本地和手动 ingest 先形成可评估的检索质量闭环，再扩大数据源范围。

## 第一批 specs 的依赖、风险和不包含范围

### 1. `knowledge-base-core`

依赖：

- `vector_store` public API 可按 namespace upsert/search/delete，且已有普通 SQLite persistent backend。
- DB runtime/store 边界已可承载 Alembic 管理的 tables。
- `knowledge_base.*` config namespace 明确默认 tenant、默认 kb、chunk size、embedding provider。

风险：

- `vector_store` 当前 API 已支持 namespace；metadata filter 不属于 vector_store MVP，KB 业务过滤应先由 KB store 负责。
- Alembic 表设计要避免后续 parser/connector/sync 字段频繁破坏兼容。
- embedding 默认路径必须 self-host 或 deterministic test double，不能落到 OpenAI Embeddings。

不包含：

- 不迁移 parser / connector 代码。
- 不实现 BM25 / hybrid search。
- 不实现 graph_search、entities、relations。
- 不做后台 sync planner 或 admin UI。

### 2. `knowledge-base-parsers-basic`

依赖：

- core 已定义 parsed section 输入或 parser 输出 dataclass。
- core ingest 可以接受 parser 输出并保留 filename/source metadata。

风险：

- Markdown/HTML 表格依赖 `pandas` 的收益与依赖成本需要评估；可用轻量 table renderer 替代。
- parser 输出若过早暴露为 public API，会限制后续 PDF/Office parser 演进。

不包含：

- 不引入 docling。
- 不处理 image/VLM。
- 不接 Confluence/Drive。
- 不实现 Office/PDF parser。

### 3. `knowledge-base-connectors-local`

依赖：

- core ingest 和 basic parsers 可用。
- config 支持本地目录白名单和 kb binding。
- 测试可用 `tmp_path` 隔离，不触碰 `data/`。

风险：

- 文件路径可能包含敏感目录；必须限制在显式配置路径下。
- mtime 不是可靠内容版本，后续 sync planner 需要 content hash。

不包含：

- 不实现后台 scheduler。
- 不实现 Confluence/Drive。
- 不实现 multi-worker。
- 不做权限 ACL。

### 4. `knowledge-base-hybrid-search`

依赖：

- core chunks table 稳定，并有可查询的 chunk rowid / chunk id 映射。
- vector_store search 可用。
- SQLite FTS5 运行环境确认。

风险：

- 中文 BM25 分词策略需要测试集验证，不能只照搬 LanceDB 字段。
- RRF 与 vector score 的组合需要可解释，避免影响 long_term_ctx token 预算。

不包含：

- 不实现 reranker。
- 不实现 query planner / translator。
- 不实现 graph_search。
- 不引入 LanceDB FTS。

## 后续实施建议

下一个 KB implementation spec 建议是 `knowledge-base-core`。它应以“手动 text/markdown ingest -> chunks -> vector_store -> search 返回 `KnowledgeChunk`”为唯一闭环，并把 parser、connector、hybrid、graph、sync 都排除在外。完成后再用 `knowledge-base-parsers-basic` 和 `knowledge-base-connectors-local` 扩大输入面。
