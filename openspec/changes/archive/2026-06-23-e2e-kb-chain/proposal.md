## Why

知识库（KB）是 agent 的核心外部知识来源：文档 ingest 写入 → 检索 → 注入 agent context → 落检索 audit trace。这条完整链路至今**只有单进程 unit/integration 覆盖**——没有一条 e2e 在真实多进程 managed 栈（platform + node + agent 三进程）下证明"ingest 进去的内容，agent 在对话里真能检索到、且检索被审计"。KB 是 agent 回答质量的命脉，回归代价高，必须有端到端守门。地基 harness（`tests/e2e/conftest.py::managed_stack` + `tests/e2e/_llm_stub.py`）已落地，正好解锁这条覆盖。

向量后端本地零外部依赖即可跑：`vector_store/backend.py::SQLiteVectorBackend` + `vector_store/embeddings.py::DeterministicEmbeddingProvider`（blake2b hash 稳定向量，100% 可复现），e2e 无需 stub embedding，检索命中可确定性断言。

## What Changes

- 新增 e2e：在多进程 managed 栈下，端到端验证 KB 完整链路：
  - **ingest → 检索命中**：经真实 ingest 路径写入一段可检索文本，经真实 retrieval `search()` 路径命中。
  - **检索结果注入 agent 对话**：经确定性 LLM stub 验证 agent 在对话中拿到了被检索出的 KB 内容（KB 内容出现在传给 LLM 的上下文里）。
  - **检索 audit trace 被记录**：检索发生时 `record_kb_retrieval()` 写下 observability trace，可被观测到。
- 新增 KB e2e helper `tests/e2e/_kb_helpers.py`（本 change 独占文件），复用已落地的多进程起栈 `managed_stack` 与确定性 LLM stub，**不重构核心 `managed_stack` fixture**。
- 进 slow/nightly lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

## Capabilities

### New Capabilities
- `e2e-kb-chain`: 多进程 managed 栈下的 KB 完整链路端到端覆盖——ingest 写入 → 检索命中 → 注入 agent 对话 → 检索 audit trace 被记录。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + KB helper `tests/e2e/_kb_helpers.py`）；复用 `tests/e2e/conftest.py::managed_stack`、`tests/e2e/_llm_stub.py`、`tests/integration/_migration_template` 既有基建
- **public API surface**：无（纯测试侧；不新增/改 src public API）
- **owned tables**：无（测试用隔离临时库；只读验证 KB DB / observability trace 落盘结构）
- **config namespace**：无
- **cross-module dependencies**：无 src 跨模块依赖（测试编排既有 platform/node/agent 三进程 + KB ingest/retrieval/inject 既有路径；不引入新 src import）
- **migration / shim**：无（复用既有起栈与迁移基建）
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture **冻结不动**（新 helper 放独占 `tests/e2e/_kb_helpers.py`，避免与并行 e2e 波撞 `conftest.py`）
- **CI**：进 `make test-e2e` slow/nightly lane，不进 per-merge `make test-pr` 门禁
