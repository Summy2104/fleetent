## Context

地基 harness 已落地：`tests/e2e/conftest.py::managed_stack` 起单 tenant 单 agent 的真实多进程栈（platform + node + agent 进程），`tests/e2e/_llm_stub.py` 提供确定性 OpenAI 兼容 SSE LLM stub。本 change 在其上加 KB 完整链路覆盖。

已核实的真实 KB 代码路径（给断言定位用）：
- **ingest**：`src/fleetent/knowledge_base/ingest/runtime.py` 的 `ingest_text()` / `ingest_parsed()`，经 `KnowledgeStore` 写 SQLite KB DB。
- **retrieval**：`src/fleetent/knowledge_base/retrieval/search.py:30` 的 `search()`（支持 vector / keyword / hybrid）。
- **注入 agent context**：`src/fleetent/knowledge_base/runtime.py` 持进程级 `_kb_db` / `_kb_vector_backend`，agent loop 调 `search()` 把命中内容注入对话。
- **向量后端（零外部依赖）**：`src/fleetent/vector_store/backend.py::SQLiteVectorBackend` + `src/fleetent/vector_store/embeddings.py:22` 的 `DeterministicEmbeddingProvider`（blake2b，稳定可复现）。
- **检索 audit**：`search.py:90` 的 `record_kb_retrieval()`（传 `KBRetrievalAuditContext`），写 observability。
- tenant 级 KB 库落盘：`tenant_router.SQLiteTenantBackend` → `<data_dir>/<tenant>/kb.db`。

> 注：KB connector scheduler 刚合并 main（commit 64c2891e），但 ingest / retrieval / inject 核心稳定；本 change **不**测 scheduler。

## Goals / Non-Goals

**Goals**：端到端证明 KB 链路四环在多进程 managed 栈下贯通——ingest 写入 → 检索命中 → 注入 agent 对话 → 检索 audit trace 被记录；helper 以新增方式提供，零 src 改动。

**Non-Goals**：不测 KB connector scheduler / webhook ingest；不测网络向量后端（Qdrant）；不重构核心 `managed_stack`；不测 KB 管理面 API（创建/归档 KB）。

## ⚠️ 关键可行性风险（apply 第一步必须先用探针先验，不得写死假设）

managed 多进程运行时下，三个观测点都**不能假设**，apply task 1 必须先用最小探针逐一定位：

1. **KB 数据落盘点**：placed agent 在 node 下运行时，其 KB 库到底落在哪？是经 `tenant_router` 落 `<data_dir>/<tenant>/kb.db`，还是落 agent home？这决定 ingest 写入的目标库与检索读取的同源库怎么对齐——**写入侧与读取侧必须命中同一物理库**，否则检索恒空。
2. **多进程下怎么把 ingest 内容喂给 agent 进程**：ingest 发生在哪个进程、agent 检索读的是不是同一份 KB DB？需确认 ingest 写入路径（CLI / HTTP / 直接落库）能让 agent 进程的 `runtime.py::_kb_db` 读到。可能需要 ingest 落盘点与 agent 进程的 KB DB 解析路径对齐（同 tenant / 同 data_dir）。
3. **检索 audit trace 怎么跨进程观测**：`record_kb_retrieval()` 写的 observability trace 落在 agent 进程侧的哪个文件 / 表？e2e 在外部进程怎么读到？需定位 trace 落盘点（agent observability store），再据此定断言。

apply 的 task 1 必须用最小探针把这三点的真实落盘 / 注入 / 观测点定位清楚，再据此写断言；任何一点假设错，断言都会假绿或假红。

## Decisions

- **新增 `tests/e2e/_kb_helpers.py`，不改 `managed_stack`**：KB 专属 helper（ingest 写入封装、检索断言、audit trace 读取）全放本 change 独占文件，并行 e2e 波不碰 → 零 `conftest.py` 合并冲突。helper 复用 `managed_stack` 起的栈与 `_llm_stub`，只在其上加 KB 写入 / 读取动作。
- **复用 `DeterministicEmbeddingProvider`，不 stub embedding**：blake2b 稳定向量天然可复现，检索命中可确定性断言（query 与文档共享 token 即命中），e2e 无需额外 mock embedding 服务。
- **注入验证走 LLM stub 可见证据**：经 `_llm_stub` 记录 / 回放传给 LLM 的上下文，断言被 ingest 的 KB 内容确实出现在 agent 发给 LLM 的 prompt 里——证明"检索结果注入了对话"，而非仅断言 `search()` 返回非空。
- **audit 断言走真实 trace 落盘点**：定位 `record_kb_retrieval()` 的 observability 落盘后，直接读该 trace 断言一次检索被记录（query / 命中数等），而非 mock。

## Risks / Trade-offs

- 三个观测点不确定（见上）→ 用 task 1 探针逐一消解，先于任何断言。
- 多进程下 ingest 与 agent 检索的 KB DB 可能不同源 → 探针必须确认写读同库；若不同源，helper 需把 ingest 定向到 agent 进程可达的 KB DB（同 tenant / data_dir）。
- 起多进程栈 + ingest 增加用例耗时 → e2e 在 slow lane，可接受。
- audit trace 可能异步落盘 → 断言前需用既有 `wait_for_condition` 轮询，避免 flaky。
