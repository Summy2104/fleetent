## 1. 确定性 eval runner 提取到 src + /evaluations 接通

- [x] 1.1 **测试（红）**：把 `tests/evaluation/test_knowledge_base_retrieval_eval.py` 改为调 **src 的** runner（如 `knowledge_base/retrieval/evaluation.py`），在标注 fixture 上断言 recall@k/MRR/hit-ranking、确定性 embedding、不碰 index。先跑见红（src runner 尚不存在）。
- [x] 1.2 **实现（绿）**：把确定性评估逻辑从 `tests/evaluation/knowledge_base_retrieval_eval.py` 提取到 `src`（fixture 仍作数据输入；**src 不 import tests**）；保确定性 embedding + 隔离存储 + read-only。跑见绿。
- [x] 1.3 **测试（红）→ 实现（绿）**：`POST /evaluations`（kb_admin_api）调 src runner，返回真实 recall@k/MRR，**替掉 `{metrics:{}, wired:False}`**；admin+viewer 可读、不碰 index。

## 2. /observation 聚合 kb_retrieval trace → proxy 指标

- [x] 2.1 **测试（红）**：新增 kb observation 聚合器（仿 `agent_observability.aggregate`）：mock `query_trace_events` 喂若干 `kb_retrieval` 事件（含 hit_count=0 的空召回）→ 断言算出 **延迟 p50/p95、zero_recall_rate、score 分布、query/hit 计数**，按 `kb_id` 过滤/聚合（跨该 KB 绑定的 agent）。先跑见红。
- [x] 2.2 **实现（绿）**：实现聚合器（复用 `query_trace_events(event_type="kb_retrieval")` 路径）；`GET /{kb_id}/observation` 调它返回 proxy 指标，**替掉 `recall_hits:0` 占位**。跑见绿。
- [x] 2.3 **测试（绿）· proxy≠recall 纪律**：断言 observation 返回**不含**需 ground-truth 的真实 recall@k/MRR 字段（不报真 recall）；citation 不在返回（defer）。

## 3. 收尾

- [x] 3.1 边界核验：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + 依赖护栏（src eval runner 不 import tests；platform 读 trace 经既有路径；不碰 agent 写路径）。
- [x] 3.2 `make test-pr` 全绿（对照 main 基线无新增失败）+ 跑相关测试 `uv run pytest tests/evaluation/test_knowledge_base_retrieval_eval.py tests/unit/<kb observation 测试> tests/integration/<kb_admin_api 测试> -q`（无新增失败）+ 覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [x] 3.3 注明：返回形状从占位变真实字段，前端 observation/evaluation 视图若依赖旧占位字段需跟进（本切片只改端点数据，UI 跟进另议）。
