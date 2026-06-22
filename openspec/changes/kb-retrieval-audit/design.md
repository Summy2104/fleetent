## Context

- 检索入口：`knowledge_base/retrieval/search.py::search(query, store, tenant_id, kb_ids, limit, mode, rerank)` → `list[KnowledgeChunk]`；`retrieval/graph_search.py::graph_search(...)`。当前不写任何 trace。
- observability 已有：`record_trace_event(TraceEvent(run_id, event_type, payload, session_id, user_id, agent_name, tenant_id))`；best-effort 范式见 `record_tool_call`（try/except、warn、吞掉、"side channel MUST NOT affect run"）；原文脱敏先例见 `_RAW_CONTENT_KEYS` + `record_injected_context._source_summary`。
- `TraceEvent` 需要 `run_id`（绑定 agent run）；但 `search()` 签名当前不带 run 上下文。

## Goals / Non-Goals

**Goals:**
- 每次检索（含空召回）尽力而为留一条 `kb_retrieval` trace：ids/scores/latency/mode/kb_ids/query-hash，绑 run 上下文。
- 隐私安全默认（不落原文）+ opt-in 明文。
- 绝不影响检索结果（best-effort side channel）；绝不写 platform 表。

**Non-Goals:**
- 不做读取/聚合端点（/observation、/evaluations = 缺口 ④）。
- 不做真 recall@k/MRR（需标注 fixture，属 ④）。
- 不调 retention（复用既有 trace retention）。

## Decisions

- **D1 · 在检索边界记录，run 上下文经"审计上下文"传入。** search/graph_search 取得一个**可选审计上下文**（`run_id/session_id/user_id/agent_name/tenant`）后，在结果就绪 + 计时后写 trace。传入方式二选一（apply 时按现有代码定）：(a) 若已有 run 级 **contextvar** → 直接读，零签名改动、自动传播；(b) 否则给 search/graph_search 加**可选参数**，由调用方（loop / long_term_ctx）传。**无审计上下文时跳过记录**（不伪造 run_id），保持 best-effort。
- **D2 · 隐私默认 A。** query 只存 `sha256(query)[:N]` hash；结果只存 ids+scores，不存 chunk 正文；沿用 `_RAW_CONTENT_KEYS` 脱敏。新增**默认关闭**的明文调试开关（config，如 `kb.retrieval_audit.plaintext: false`）；仅开启后 payload 才含 raw query/chunk。
- **D3 · 事件 schema**：`event_type="kb_retrieval"`，payload = `{result_ids:[...], scores:[...], hit_count, latency_ms, mode, kb_ids, query_hash}`；明文开关开时追加 `raw_query` / `raw_chunks`。新增 `observability` 辅助 `record_kb_retrieval(...)` 封装构造 + best-effort（镜像 `record_tool_call`）。
- **D4 · best-effort**：写入包 try/except → warn 吞掉，检索结果原样返回、不抛错。计时 = 包住实际检索调用（不含 trace 写入耗时）。
- **D5 · 边界**：`knowledge_base/retrieval` 依赖 `observability`（agent 侧 side channel，允许）；**绝不** import `knowledge_base/ingest`（守 `retrieval ✗→ ingest` 护栏）、**绝不** import/写 platform。standalone 下照常工作。
- **D6 · 覆盖全模式**：vector / keyword / hybrid（含 rerank）四条 + graph_search 全部 instrument，别漏 mode（keyword 是早 return 分支，注意）。

## Risks / Trade-offs

- **签名/上下文穿透**：search() 被多处调用。优先用现有 run contextvar（零签名改动）；若无则加可选参数、确保所有生产调用方传上下文（否则审计丢 run 绑定）。apply 时先探明有无 contextvar 再定，避免大面积改签名。
- **别漏 keyword 早 return 分支**：`search()` 里 `mode=="keyword"` 直接 `return store.search_keyword(...)`，instrument 要包住这条，否则 keyword 检索不留痕。
- **best-effort 的纪律**：trace 写入异常必须吞（warn），任何"trace 失败导致检索抛错"都是 bug；测试需覆盖"trace 写失败 → 检索仍正常返回"。
- **隐私开关误开风险**：明文开关默认 OFF 且需显式开启；测试覆盖"默认配置下 trace 无 raw query/chunk"。
- **查询 hash 成本**：sha256 一个 query 字符串，可忽略。
