## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段3**（在阶段4 后实施，与阶段4 **设计合并**破 memory↔reflection 循环）。`reflection.py` 是 1643 行的混合体，缠着三块职责：① 自进化分析引擎（读 trace/memory/KB 产出 findings + 改进建议）；② 提案的变更审批工作流（approve/reject/apply，带 reviewer/owner）；③ 管理接口（list/get proposal、趋势汇总、报告/提案存储）。按纲领判据，自进化引擎是 **agent 元能力**（纵向，§2.3）、审批是 **governance 门**（横切，§2.2）、管理接口是 **platform 薄壳**。本 change 三刀切并各归其位，同时破 memory↔reflection 循环。

## What Changes

- **reflection 提为顶层** `reflection/`（agent 元能力，纵向贯穿各能力域）。**三刀切，引擎内不再细分**（memory 反思 / KB 反思 / skill 机会暂留一块，内部细分后置）：
  - **自进化引擎** → agent `reflection/`：`run_reflection` / `run_kb_reflection_report` / `generate_memory_maintenance_proposals` / `generate_skill_proposals` / findings 生成 / `_read_memory_signals`。读 memory / `knowledge_base.retrieval` / trace，产出 proposal。
  - **proposal/report 存储** → 留 agent `reflection/`（自进化产物 = agent 数据，§10）：proposal/report 表的 CRUD（`_insert/_update/_get/_save_report`）。
  - **变更审批门** → `governance/`：approve/reject/expire/apply（skill + memory maintenance + shared-memory proposal）。是 `permission_gate` 的**异步非阻塞泛化**（proposal 持久化、延后经 IM/console resolve），与 permission_gate 同列 governance。`resolve()` 后**回调对应真相源写接口**落地。
  - **管理 API** → **新建** `platform/reflection_management/`：list/get proposal（各类型）、趋势查询（`get_reflection_trend_summary` + `_trend_*`）、skill/KB proposal 的 console 评审暴露面。
- **审批渠道按 proposal 类型路由**（§10）：user/shared memory → IM（agent 自主，`reply_func` 推送）；skill/KB → platform console（管理员审）。
- **破 memory↔reflection 循环**：审批门居中。reflection → memory/KB.retrieval（**读**，方向正确）；memory ✗→ reflection（移除 `memory/shared.py`、`memory/trends.py` 的 lazy-import）；governance 门 → memory.shared 写接口（落地 shared-memory proposal）。
- **依赖护栏**：reflection ✗→ `knowledge_base.ingest`、✗→ platform；写经 governance 门。

## Capabilities

### New Capabilities
- `self-evolution-split`: 把 reflection 三刀切边界固化为 spec——自进化引擎（agent 元能力，只读 memory/KB.retrieval/trace + 产 proposal）、变更审批门（governance，permission_gate 异步泛化，resolve→真相源写）、管理 API（platform/reflection_management 薄壳）、proposal/report 存 agent 数据、审批渠道按类型路由、memory↔reflection 循环经门破、依赖护栏。

### Modified Capabilities
- `reflection`：行为不变，按引擎/门/管理 三处归位；delta 在 `self-evolution-split` 表达。
- `permission-gate`：不改其契约；governance 新增**并列**的异步 proposal 审批门（泛化同源，非改 permission_gate 本身）。
- `skill-proposal-review`：skill proposal 的管理/评审暴露面迁到 `reflection_management`；skill_management 的评审 inbox 改为消费 reflection_management（行为不变）。

## Impact

- 拆 `reflection.py`(1643) 为：agent `reflection/`（引擎 + proposal/report 存储）、`governance/`（审批门）、`platform/reflection_management/`（新建，管理 API）。
- 调用方：`memory/shared.py`（移除 reflection lazy-import，写接口供门回调）、`memory/trends.py`（聚合迁 reflection_management）、`platform/skill_management/skill_admin_api.py`（`reflection_list_proposals`/`reflection_proposal_diff`/apply 迁 reflection_management）。
- **依赖**：阶段1（vector_store）、阶段2（KB retrieval 边界）、阶段4（memory 顶层 + 写接口面）；启用阶段4 标 TODO 的 `memory ✗→ reflection` 护栏。
- CLAUDE.md 契约文字留阶段5 统一改。
- **不含**：自进化算法变更、引擎内部细分（后置）、reflection 异步调度（cron，纲领 §9，重构后再加）。
