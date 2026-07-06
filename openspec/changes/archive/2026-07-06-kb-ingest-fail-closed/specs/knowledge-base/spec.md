# knowledge-base — Delta

## MODIFIED Requirements

### Requirement: Manual text ingest and chunk indexing
系统 SHALL 支持手动导入 text / markdown 内容，生成 deterministic chunks 并写入 vector_store。manual ingest 的文档身份 SHALL 为 `(tenant_id, kb_id, source, filename)`；对同一身份重复导入时，系统 SHALL 以覆盖（overwrite）语义替换旧文档，使该身份在库中始终只保留最新一份，不产生重复 document 或 chunk。

文档写入 SHALL **fail-closed**：全部 chunk 的向量化 SHALL 在任何持久化写（document / chunk / FTS / 向量删旧）之前于内存完成；embedding 失败时 SHALL 使整文档导入失败，库中 MUST NOT 留下该文档的任何残留（document、chunk、FTS、向量均无），overwrite 场景下旧文档 SHALL 保持原样不被破坏。

#### Scenario: Ingest creates document and chunks
- **WHEN** 调用 `ingest_text(filename, content, tenant_id, kb_id, source, source_url)`
- **THEN** 系统创建 document record
- **AND** 系统按 deterministic chunking 创建有序 chunks

#### Scenario: Empty content is rejected
- **WHEN** 导入内容为空或全空白
- **THEN** 系统 fail fast

#### Scenario: Chunks are indexed in vector store
- **WHEN** ingest 创建 chunk
- **THEN** 系统调用 `vector_store.upsert(chunk_id, chunk_content, knowledge_namespace(tenant_id, kb_id))`

#### Scenario: embedding 故障时整文档干净失败
- **WHEN** 导入过程中 embedding 调用失败（如 embedding 服务不可达 / 模型不存在）
- **THEN** 导入以异常失败，错误上抛（不静默）
- **AND** 库中不存在该文档的任何残留：document 列表无此文档、无 chunk、无 FTS 条目、无向量
- **AND** 若为同身份重复导入，此前已存在的旧文档及其全部派生数据保持原样可检索

#### Scenario: Ingest is tenant and kb scoped
- **WHEN** 同一 filename 被导入不同 tenant 或 kb
- **THEN** records 与 vector namespace 相互隔离

#### Scenario: Re-ingest same identity overwrites previous document
- **WHEN** 以相同 `(tenant_id, kb_id, source, filename)` 再次调用 `ingest_text` 或 `ingest_parsed`
- **THEN** 系统先删除旧 document 及其全部派生数据（chunks、chunks_fts、对应 `vector_store` 向量、该文档的 `kb_entity_mentions` 与 `kb_relations`，并 GC 由此产生的孤儿 `kb_entities`）
- **AND** 系统写入新版本的 document 与 chunks
- **AND** search 与 graph_search 只返回新版本内容，不返回旧版本残留

#### Scenario: Re-ingest does not duplicate
- **WHEN** 同一身份连续导入两次内容
- **THEN** 该身份在库中只存在一份 document
- **AND** 该 document 的 chunk 数量与单次导入一致，无重复 chunk

#### Scenario: Differing identity does not overwrite
- **WHEN** filename 相同但 `source` 不同（或 tenant/kb 不同）
- **THEN** 视为不同文档，各自独立保留，互不覆盖
