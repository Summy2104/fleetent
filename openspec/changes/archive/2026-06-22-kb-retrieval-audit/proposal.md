## Why

KB 检索目前**零可观测**：`search()` / `graph_search()` 跑完不留任何痕迹，无法看检索质量（命中了哪些 doc、score 分布、延迟、空召回率）。这是 KB 生产化运维的缺口，也是 `/observation` / `/evaluations`（缺口 ④ kb-evaluation-observation）的**前置数据源**——没有检索 trace，线上 proxy 指标算不出来。

关键约束（[[kb-production-gaps-plan]] #3 已定）：**audit 写 observability trace、归 agent 侧，绝不写 platform 表**（守 agent↔platform 解耦）。检索是 agent 消费的读路径，audit 作为 side channel 落 observability。

> 这是 KB 生产化缺口 ③（车道 B）。与正在执行的 `unify-agent-ingress-principal`（#3）零文件重叠（本 change 只碰 `knowledge_base/retrieval` + `observability`，不碰 server.py/forwarder/agent_app）。

## What Changes

- **instrument 检索**：`search()` / `graph_search()` 完成后**尽力而为（best-effort）**写一条 `kb_retrieval` observability trace 事件，载：result doc/chunk ids、scores、latency_ms、mode、kb_ids、tenant、query **hash**。
- **隐私安全默认（决策 A）**：默认**不存** raw query 原文、**不存** chunk 正文——query 只存 hash、结果只存 ids+scores。沿用既有 `_RAW_CONTENT_KEYS` 脱敏先例。
- **opt-in 明文调试开关**（默认关闭）：显式开启后才记 raw query/chunk，供排查；默认关。
- **best-effort 不影响检索**：trace 写失败（DB 不可用等）只 warn 并吞掉，**MUST NOT** 改变检索结果或抛错（镜像 `record_tool_call` 契约）。
- **绑定 run 上下文**：audit 事件带 run_id/session_id/user_id/agent_name（由调用方提供的审计上下文），使"按用户/会话看检索质量"可行。

### 不在本切片（deferred）
- `/observation` / `/evaluations` 端点的**读取/聚合**（= 缺口 ④ kb-evaluation-observation，依赖本切片产出的 trace）。
- 真 recall@k/MRR（需标注 fixture，属 ④ 的离线评估，线上算不出）。
- 专用 retention 策略调参（先复用现有 trace retention，retention 细化留 ④/后续）。

## Capabilities

### New Capabilities
- `kb-retrieval-audit`: 检索（vector/keyword/hybrid/graph）尽力而为写 observability trace（ids/scores/latency/query-hash），隐私安全默认（不存原文）、可 opt-in 明文、绝不影响检索、绝不写 platform 表。

### Modified Capabilities
（无）

## Impact

- **owning packages**：`knowledge_base`（`retrieval/search.py`、`retrieval/graph_search.py` instrument）、`observability`（复用 `record_trace_event` + 脱敏；可能加 `record_kb_retrieval` 辅助 + `kb_retrieval` event_type）
- **public API surface**：`search()`/`graph_search()` 可能加**可选审计上下文参数**（run_id/session_id/user_id/agent_name/tenant），向后兼容（不传则不记，或记无 run 绑定的最小事件）
- **owned tables**：无新增——写既有 traces（agent_state.db，per-agent 嵌入式迁移）。**绝不写管理库**
- **config namespace**：新增"检索 audit 明文调试开关"（默认 OFF）+（可选）audit 启停开关
- **cross-module dependencies**：`knowledge_base/retrieval` → `observability`（agent 侧 side channel，允许）；**不碰** `knowledge_base/ingest`（守 `retrieval ✗→ ingest` 护栏）；不碰 platform
- **migration / shim**：无 schema/迁移（trace 是既有表，新 event_type 不需建表）
- 与 agent↔platform 解耦一致：audit 落 agent 侧 observability，platform 要看时读 agent 侧 trace（缺口 ④），不要求 agent 反写 platform
