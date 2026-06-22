## ADDED Requirements

### Requirement: 检索尽力而为写 observability trace

KB 检索（`search` 的 vector/keyword/hybrid 模式与 `graph_search`）完成后 SHALL 尽力而为写一条 `kb_retrieval` observability trace 事件，记录：命中的 doc/chunk **ids**、对应 **scores**、**latency_ms**、检索 **mode**、**kb_ids**、**tenant**，以及 query 的 **hash**。事件在可得时 SHALL 绑定 run 上下文（run_id/session_id/user_id/agent_name），使"按用户/会话观测检索质量"可行。

audit 是 **side channel**：trace 写入失败（存储不可用等）SHALL 只 log warning 并吞掉，**MUST NOT** 改变检索结果、MUST NOT 抛错中断检索或所在 run（镜像 `record_tool_call` 契约）。

#### Scenario: 一次检索产生一条 trace

- **WHEN** agent 跑一次 KB 检索且命中若干 chunk
- **THEN** 写出一条 `kb_retrieval` 事件，含 result ids + scores + latency_ms + mode + kb_ids + query hash，绑定该 run

#### Scenario: 空召回也留痕

- **WHEN** 一次检索命中 0 条
- **THEN** 仍写出 `kb_retrieval` 事件（result ids 为空、记录 latency/mode/query hash），供观测空召回率

#### Scenario: trace 写失败不影响检索

- **WHEN** 写 trace 时存储不可用
- **THEN** 检索照常返回结果，失败被 log warning 吞掉，run 不受影响

### Requirement: 隐私安全默认（不存原文，可 opt-in）

audit **默认 SHALL NOT** 持久化 raw query 原文与 chunk 正文：query 仅以 **hash** 记录，结果仅记 ids + scores。沿用既有原文脱敏约定（`_RAW_CONTENT_KEYS`）。系统 SHALL 提供一个**默认关闭**的明文调试开关；仅在显式开启后才记录 raw query/chunk 文本。

#### Scenario: 默认不落原文

- **WHEN** 默认配置下发生检索
- **THEN** trace 中 query 为 hash、无 chunk 正文、无 raw query 文本

#### Scenario: opt-in 后才记明文

- **WHEN** 显式开启明文调试开关后发生检索
- **THEN** trace 才包含 raw query/chunk 文本（供排查）

### Requirement: audit 归 agent 侧，绝不写 platform 表

检索 audit SHALL 只写 agent 侧 observability trace（per-agent 既有 traces 存储），**MUST NOT** 写任何 platform 管理表。`knowledge_base/retrieval` 为此可依赖 `observability`，但 MUST NOT 依赖 `knowledge_base/ingest`（守既有 `retrieval ✗→ ingest` 护栏）、MUST NOT 依赖 platform。

#### Scenario: 不触碰 platform

- **WHEN** 检索 audit 写入
- **THEN** 只落 agent 侧 trace 存储，无任何对 platform 管理表的写入；standalone（无 platform）下检索 + audit 正常工作
