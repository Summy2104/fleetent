## 1. KB schema 加 embedding 身份列（TDD）

- [x] 1.1 测试先行：迁移后 `knowledge_bases` 有 `embedding_model` / `embedding_dimensions` 列；旧行（迁移前建的）该两列为 NULL。见红
- [x] 1.2 实现：`knowledge_base/core/migrations.py` 的 KB_MIGRATIONS 追加一个 forward-only 版本（`_BASE_MIGRATIONS[-1][0]+1` 之后的下一个版本号），`ALTER TABLE knowledge_bases ADD COLUMN embedding_model TEXT` + `ADD COLUMN embedding_dimensions INTEGER`。见绿
- [x] 1.3 `core/store.py`（KnowledgeStore）加读/写该身份的方法（get/set embedding identity by tenant+kb）

## 2. 取当前 embedding 身份（vector_store 暴露）

- [x] 2.1 `vector_store/runtime.py`：暴露当前 `_embedding` 的 `model` + `dimensions`（HttpEmbeddingProvider 有；DeterministicEmbeddingProvider 无 model → 用约定 `deterministic/<dims>`）。先写取身份的单测见红→实现见绿

## 3. ingest stamp + 拒绝混模型（TDD）

- [x] 3.1 测试先行：首次 ingest 后 KB 记录下当前 embedding 身份；再用不同 model/dims ingest → 拒绝报错。见红
- [x] 3.2 实现：ingest 写向量处（`ingest/runtime.py` upsert / `replace_document` 链路）——若 KB 身份未记录则 stamp;已记录则比对,不一致 raise 清晰错误。见绿

## 4. 检索校验硬失败（TDD）

- [x] 4.1 测试先行：检索 embedding 身份 ≠ KB 记录 → 硬失败报清晰错误（而非空/噪声）;一致 → 正常检索。见红
- [x] 4.2 实现：`retrieval/search.py:122` `embed_text(query)` 之前（或其调用上游)插入身份比对,不匹配 raise（错误信息含 KB 建库 vs 当前检索的 model/dims）。见绿
- [x] 4.3 确认该错误**不被** `long_term_ctx` 的 `_retrieve_with_timeout` 静默吞成空——应作为可见错误冒出（或至少 warn 级日志明确指出不匹配,不静默 empty)

## 5. 默认 embedding 两端对齐

- [x] 5.1 `agent_config` 默认 embedding 路由 与 `kb-service.yaml.example` 的 `embedding`（现 default-embedding/dim64 vs bge-small/dim384）对齐为同一 model+dimensions+endpoint;更新相关断言测试

## 6. 收尾门禁

- [x] 6.1 `openspec validate kb-embedding-consistency --strict`
- [x] 6.2 `make test-pr` + `make test-integration-ci` 全绿
- [x] 6.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [x] 6.4 功能分支 `openspec archive kb-embedding-consistency`（同步 knowledge-base spec）
- [x] 6.5 所有 checkbox 标 `[x]`
