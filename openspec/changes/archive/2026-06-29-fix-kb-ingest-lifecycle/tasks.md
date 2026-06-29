## 1. Delete 级联清理（D1）

- [x] 1.1 写 integration 测试：`delete(document_id)` 后该文档的 `kb_entity_mentions` 与 `kb_relations` 被清理，`graph_search` 不再返回指向该文档的图证据（见红）
- [x] 1.2 写 integration 测试：删文档后零剩余 mention 且不被任何剩余 relation 引用的 canonical `kb_entities` 被 GC（见红）
- [x] 1.3 写 integration 测试：共享 entity（仍被另一未删文档的 mention 或 relation 引用）在删除后存活（见红）
- [x] 1.4 写 integration 测试：`delete` 幂等——删不存在/已删文档不报错（见红）
- [x] 1.5 在 `store.delete_document` 的同一事务内级联删除 `kb_entity_mentions`(按 `document_id`)、`kb_relations`(按 `evidence_document_id`)，并按 D3 双条件 GC 孤儿 `kb_entities`；跑 1.1–1.4 见绿
- [x] 1.6 确认 vector_store 删除顺序不变、retrieval✗→ingest 护栏不破；跑受影响 integration 层无新增失败

## 2. Re-ingest overwrite（D2）

- [x] 2.1 写 integration 测试：同 `(tenant_id, kb_id, source, filename)` 二次 ingest 后库中只存一份 document、chunk 数与单次一致、无重复（见红）
- [x] 2.2 写 integration 测试：二次 ingest 后旧 chunks/向量/该文档 mentions/relations 被替换，search 与 graph_search 只返回新版本（见红）
- [x] 2.3 写 integration 测试：filename 相同但 `source`（或 tenant/kb）不同 → 视为不同文档，互不覆盖（见红）
- [x] 2.4 写 integration 测试：已存在同身份重复历史行时，覆盖后收敛为一份（见红）
- [x] 2.5 在 ingest 路径（`ingest_text` / `ingest_parsed` → `_ingest_chunks`）实现按身份查旧 document 并复用 1.5 的删除级联（delete-then-insert），命中多行则全删再插；跑 2.1–2.4 见绿
- [x] 2.6 确认 `ingest_text` / `ingest_parsed` public API 签名不变、connector 路径行为不变；跑受影响 integration 层无新增失败

## 3. 收尾验证

- [x] 3.1 跑 `make test-pr` 与 `make test-integration-ci`，两者全绿（无新增失败）
- [x] 3.2 `uv run ruff format/check` 改动文件、`openspec validate fix-kb-ingest-lifecycle` 通过
- [x] 3.3 更新 `docs/capabilities/knowledge-base.md`：移除"重新导入同名文档"待决项、记录 overwrite 语义与 delete 级联清理行为（非代码产物，人工确认后再 commit）
