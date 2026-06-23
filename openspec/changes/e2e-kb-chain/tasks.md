## 1. 定位真实落盘 / 注入 / 观测点（探针，先于断言）

- [ ] 1.1 **探针 A — KB 落盘点**：用既有 `managed_stack` 起单 tenant 单 agent，经真实 ingest 路径写一条带特征关键词的数据，在文件系统 / `tenant_router` 解析下定位该 KB 数据的真实物理库路径（`<data_dir>/<tenant>/kb.db` 还是其他）。记录结论。**不写死假设**。
- [ ] 1.2 **探针 B — 写读同源**：确认 ingest 写入的 KB 库与 agent 进程检索路径（`knowledge_base/runtime.py::_kb_db`）读取的 KB 库是**同一物理库**（同 tenant / 同 data_dir）。若不同源，记录如何把 ingest 定向到 agent 进程可达的库。
- [ ] 1.3 **探针 C — 注入可见证据**：确认 `_llm_stub` 能记录 / 回放 agent 传给 LLM 的上下文，定位"被检索 KB 内容是否出现在 prompt"的可断言观测点。
- [ ] 1.4 **探针 D — audit trace 落盘点**：触发一次检索，定位 `record_kb_retrieval()` 写的 observability trace 在 agent 侧的真实落盘点（文件 / 表），确认 e2e 外部进程能读到。记录结论。

## 2. KB e2e helper（`tests/e2e/_kb_helpers.py`）

- [ ] 2.1 **测试（红）**：在 `tests/e2e/_kb_helpers.py` 写 KB 写入 / 检索断言 / audit 读取的最小 helper，并写一个最小用例——经 helper 在 `managed_stack` 栈上 ingest 一条数据、确认 KB 库就位。先跑见红。
- [ ] 2.2 **实现（绿）**：据探针 A/B 结论实现 helper（复用 `managed_stack` 与 `_llm_stub`，**不改核心 fixture**）。跑见绿。

## 3. E2E-1 ingest → 检索端到端命中

- [ ] 3.1 **测试（红）**：用 helper：ingest 一段带特征关键词文本 → 用含该关键词的 query 经真实 retrieval `search()` 检索 → 断言返回非空且命中含写入特征内容（用 `DeterministicEmbeddingProvider`，不 stub embedding）。先跑见红。
- [ ] 3.2 **绿**：让它过（若红，定位是 ingest / 落盘 / 检索哪段——这正是 e2e 要抓的链路回归）。

## 4. E2E-2 检索结果注入 agent 对话

- [ ] 4.1 **测试（红）**：用 helper：先 ingest 带特征关键词 KB 内容 → 经 agent 对话发起会触发 KB 检索的提问 → 据探针 C 经 `_llm_stub` 记录断言该 KB 特征内容出现在 agent 传给 LLM 的上下文中。先跑见红。
- [ ] 4.2 **绿**：让它过。

## 5. E2E-3 检索 audit trace 被记录

- [ ] 5.1 **测试（红）**：用 helper：经 agent 对话触发一次 KB 检索后，据探针 D 在 agent 侧 observability 落盘点断言存在一条对应本次检索的 KB retrieval audit trace（含 query / 命中信息）；用 `wait_for_condition` 轮询避免 flaky。先跑见红。
- [ ] 5.2 **绿**：让它过。

## 6. 收尾 + lane

- [ ] 6.1 `make test-e2e` 跑这批（含新 helper + 3 测试）；确认**不在** `make test-pr` 里。
- [ ] 6.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [ ] 6.3 边界自检：仅新增 `tests/e2e/_kb_helpers.py` + 本 change 的 test 文件；**未改** `tests/e2e/conftest.py::managed_stack`、未改任何 src。如确需改核心 fixture 或 src，停下说明（违反并行纪律）。
