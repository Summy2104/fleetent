## 1. observability：kb_retrieval 事件辅助 + 脱敏

- [x] 1.1 **测试（红）**：在 `tests/unit/`（如 `test_kb_retrieval_audit.py`）测 `observability` 新辅助 `record_kb_retrieval(...)`：给定 ids/scores/latency/mode/kb_ids/query + run 上下文，构造出 `event_type="kb_retrieval"` 的 TraceEvent，payload 含 ids/scores/hit_count/latency_ms/mode/kb_ids/**query_hash**、**默认无 raw_query/raw_chunks**；写入失败被吞（warn、不抛）。先跑见红。
- [x] 1.2 **实现（绿）**：`observability` 加 `record_kb_retrieval(...)`：构造 payload（query→`sha256[:N]` hash；沿用 `_RAW_CONTENT_KEYS` 脱敏；明文开关 OFF 时不含原文）+ best-effort `record_trace_event`（镜像 `record_tool_call` 的 try/except/warn/吞）。跑见绿。

## 2. instrument search()（vector/keyword/hybrid，含 rerank）

- [x] 2.1 **测试（红）**：`tests/unit/test_knowledge_base_retrieval_contracts.py`（或新文件）用 fake store + patch `record_kb_retrieval`：调 `search()` **四条路径**（vector/keyword/hybrid/hybrid+rerank）各断言写了一条 kb_retrieval（含正确 mode、result ids+scores、query_hash、绑 run 上下文）；**空召回**也写一条（ids 空）；**patch 写入抛异常 → search 仍正常返回结果**（best-effort）。先跑见红。
- [x] 2.2 **实现（绿）**：`retrieval/search.py::search` 计时包住实际检索（含 `mode=="keyword"` 早 return 分支！），结果就绪后调 `record_kb_retrieval(...)`；run 上下文经现有 run contextvar（先探明）或新增**可选审计上下文参数**传入，无上下文则跳过记录（不伪造 run_id）。跑见绿。

## 3. instrument graph_search()

- [x] 3.1 **测试（红）**：`test_kb_graph_search_helpers.py`（或新文件）：`graph_search()` 写一条 kb_retrieval（mode 标记 graph）、空召回留痕、写失败不影响结果。先跑见红。
- [x] 3.2 **实现（绿）**：`retrieval/graph_search.py::graph_search` 同 2.2 模式 instrument。跑见绿。

## 4. 隐私开关 + 边界 + 收尾

- [x] 4.1 **测试（红）**：(a) **默认配置** → trace 无 raw_query/raw_chunks（只 hash+ids）；(b) **显式开启**明文调试开关 → trace 才含 raw query/chunk。新增配置项（如 `kb.retrieval_audit.plaintext`，默认 `false`）。先跑见红。
- [x] 4.2 **实现（绿）**：接线明文开关（默认 OFF），open 时 payload 追加 raw。跑见绿。
- [x] 4.3 **边界核验**：跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + 依赖护栏测试，确认 `retrieval → observability` 允许、`retrieval ✗→ ingest` 未破、未引入 platform import。
- [x] 4.4 **收尾**：`make test-pr` 全绿（对照 main 基线无新增失败）+ 跑相关单测 `uv run pytest tests/unit/test_kb_retrieval_audit.py tests/unit/test_knowledge_base_retrieval_contracts.py tests/unit/test_kb_graph_search_helpers.py -q`（无新增失败）+ 覆盖率门禁 `make test-unit-ci`（--fail-under=76，本 change 新增代码主要被单测覆盖，注意不要拉破）。
