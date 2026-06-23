## ADDED Requirements

### Requirement: KB 链路 e2e fixture / helper

项目 SHALL 提供一组 KB e2e helper（如 `tests/e2e/_kb_helpers.py`），在真实多进程 managed 栈下封装 KB 写入（ingest）、检索断言、检索 audit trace 读取等动作，复用既有 `managed_stack` 多进程起栈基建与确定性 LLM stub。该 helper SHALL 以**新增**方式提供，**不重构**核心 `managed_stack` fixture（避免与并行 e2e 波撞 `conftest.py`）。

#### Scenario: 复用 managed 栈起栈并提供 KB 写读封装

- **WHEN** e2e 用该 helper 在 `managed_stack` 起的多进程栈上执行 KB 操作
- **THEN** helper 能向 agent 进程可达的 KB 库写入一条可检索数据，并能经真实检索路径读取，且不改动核心 `managed_stack` fixture

### Requirement: ingest → 检索 端到端命中 e2e

SHALL 有一条 e2e 验证：经真实 ingest 路径写入的一段文本，经真实 retrieval `search()` 路径能被检索命中（命中内容与写入内容对应），全程在多进程 managed 栈下、用 `DeterministicEmbeddingProvider` 确定性向量，不 stub embedding。

#### Scenario: ingest 写入的内容可被检索命中

- **WHEN** 向 KB ingest 一段带特征关键词的文本，再用包含该关键词的 query 经 retrieval `search()` 检索
- **THEN** 检索返回非空，且命中 chunk 包含写入的特征内容

### Requirement: 检索结果注入 agent 对话 e2e

SHALL 有一条 e2e 验证：被 ingest 的 KB 内容在 agent 对话中被检索并注入上下文——经确定性 LLM stub 可见证据断言该 KB 内容确实出现在 agent 发给 LLM 的 prompt 里。

#### Scenario: agent 对话拿到被检索的 KB 内容

- **WHEN** 先 ingest 一段带特征关键词的 KB 内容，再经 agent 对话发起一个会触发 KB 检索的提问
- **THEN** 经 LLM stub 记录可观测到该 KB 特征内容出现在 agent 传给 LLM 的上下文中，证明检索结果被注入对话

### Requirement: 检索 audit trace 被记录 e2e

SHALL 有一条 e2e 验证：KB 检索发生时，`record_kb_retrieval()` 写下的 observability trace 被记录、可观测（含本次检索的 query / 命中信息）。

#### Scenario: 一次检索产生一条 audit trace

- **WHEN** 经 agent 对话触发一次 KB 检索后
- **THEN** 在 agent 侧 observability 落盘点可观测到一条对应本次检索的 KB retrieval audit trace

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程 KB e2e SHALL 在独立 slow/nightly lane 运行（`make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁
- **THEN** 不运行本 change 的多进程 KB 链路 e2e（它们在独立 lane）
