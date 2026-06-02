## ADDED Requirements

### Requirement: Knowledge-base combined embedding evaluation
系统 SHALL 在 combined embedding evaluation 中覆盖 knowledge-base retrieval，验证 KB search 经由
vector-store embedding / reindex 路径后的召回行为。

#### Scenario: Knowledge-base retrieval fixture is explicit
- **WHEN** evaluation runner 加载 combined embedding fixture
- **THEN** fixture 包含 KB documents、KB queries、expected KB snippets 和 forbidden KB snippets

#### Scenario: Knowledge-base index is rebuilt through public reindex
- **WHEN** deterministic combined embedding evaluation 运行
- **THEN** runner 调用 `vector_store.reindex(ReindexRequest(owner="knowledge_base", tenant_id=..., kb_id=...))`

#### Scenario: Expected KB snippets are retrieved
- **WHEN** KB query 运行完成
- **THEN** runner 验证 expected KB snippets 出现在 `knowledge_base.search()` top-k 结果中

#### Scenario: Forbidden KB snippets are rejected
- **WHEN** KB query 运行完成
- **THEN** runner 验证 forbidden KB snippets 不出现在 `knowledge_base.search()` top-k 结果中
