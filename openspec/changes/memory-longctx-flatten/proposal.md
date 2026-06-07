## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段4**（在阶段3 前实施：memory 是 reflection / long_term_ctx 的被依赖项，先就位）。解散 intelligence/ 的承接步：把 `memory`（agent 记忆：提取/检索/自维护/shared 核心）和 `long_term_ctx`（上下文聚合，取**独立顶层方案 A**）提为顶层；同时把 shared-memory 的人工录入审计剥到 platform 薄壳，能力本体留 agent 侧。memory↔reflection 的提案链循环与阶段3 **设计合并**，实际断点随阶段3 的 governance 审批门落地。

## What Changes

- **memory 提为顶层** `memory/`（agent 能力：extraction / search / maintenance / shared 核心 / trends），`store` 作为域内 core（**不强制读写分离**——见 design D3）。
- **long_term_ctx 提为顶层包** `long_term_ctx/`（`__init__` + `_policy`，方案 A 独立顶层），对话内被 `runtime/loop` 调用，聚合 memory + `knowledge_base.retrieval`。
- **shared-memory 控制面薄壳**：人工录入的**审计记录**（`record_shared_memory_admin_audit`，写治理审计）→ platform 薄壳；能力本体（`create/update/archive/search/get/list/iter`、`apply_shared_memory_proposal`）留 agent 侧 memory.shared。
- **memory↔reflection 循环（与阶段3 交叉）**：现状 `memory/shared.py`、`memory/trends.py` lazy-import `reflection`。目标依赖方向 = memory ✗→ reflection、审批门在 governance 居中。本阶段保留 lazy-import 经 shim 可用，**实际断点在阶段3**（governance 审批门 resolve 后回调 memory.shared 写接口）；本阶段先把 memory.shared 的写接口面定清楚，供阶段3 的门调用。
- **依赖**：`long_term_ctx` → `memory` + `knowledge_base.retrieval` + `vector_store`；`memory` → `vector_store` + 域内 `store`。

## Capabilities

### New Capabilities
- `memory-longctx-flatten`: 把 memory / long_term_ctx 顶层化的边界契约固化为 spec——memory 顶层 + store 单接口（护栏约束、无读写 Protocol）、long_term_ctx 独立顶层包（不并入 runtime）、shared-memory 审计薄壳归 platform、能力本体留 agent、依赖护栏（memory✗→long_term_ctx/reflection、组件✗→platform）。

### Modified Capabilities
- `memory-layer` / `long-term-ctx`：行为不变，仅顶层化与边界归位；delta 在 `memory-longctx-flatten` 表达，本体行为契约不动。

## Impact

- 物理移动 `memory/`（8 文件）、`long_term_ctx.py` + `long_term_ctx_policy.py` → `long_term_ctx/{__init__,_policy}.py`，留 re-export shim。
- 调用方：`runtime/loop`（memory extraction + long_term_ctx 构建上下文）、`agent_config`（long_term_ctx_policy）、`admin_cli/shared_memory`（platform，审计剥离）。
- `record_shared_memory_admin_audit` 的审计写迁到 platform 薄壳。
- **依赖**：阶段1（vector_store）、阶段2（KB retrieval 边界）；与阶段3 在 shared-memory 提案链上交叉（设计合并）。
- CLAUDE.md 契约文字留阶段5 统一改。
- **不含**：记忆提取/检索算法变更、policy 语义变更、reflection 拆分本身（阶段3）。
