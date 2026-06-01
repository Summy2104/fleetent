## ADDED Requirements

### Requirement: Memory semantic retrieval embedding evaluation
系统 SHALL 提供 memory semantic retrieval embedding evaluation fixture，用于验证 memory search 经由
vector-store embedding / reindex 路径后的召回行为。

#### Scenario: Memory retrieval fixture is explicit
- **WHEN** evaluation runner 加载 combined embedding fixture
- **THEN** fixture 包含 memory records、memory queries、expected memory snippets 和 forbidden memory snippets

#### Scenario: Memory index is rebuilt through public reindex
- **WHEN** deterministic combined embedding evaluation 运行
- **THEN** runner 调用 `vector_store.reindex(ReindexRequest(owner="memory", user_id=...))`

#### Scenario: Expected memory snippets are retrieved
- **WHEN** memory query 运行完成
- **THEN** runner 验证 expected memory snippets 出现在 `memory_layer.search()` top-k 结果中

#### Scenario: Forbidden memory snippets are rejected
- **WHEN** memory query 运行完成
- **THEN** runner 验证 forbidden memory snippets 不出现在 `memory_layer.search()` top-k 结果中
