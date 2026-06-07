> **状态：DRAFT — 待 Randy 讨论修订**。本 change 含多个未决设计决策（见末尾），design/tasks 待讨论后补。

## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段3**。`reflection.py` 是 1643 行的混合体，缠着三块职责：① 自进化分析引擎（读 trace/memory/KB 产出 findings + 改进建议）；② 提案的审批工作流（approve/reject/apply，带 reviewer）；③ 趋势汇总 + 报告/提案存储。按纲领判据，自进化引擎是 **agent 元能力**、审批是 **governance 门**、管理接口是 **platform 薄壳**。本 change 把它拆开并各归其位。

## What Changes（轮廓，细节待讨论）

- **reflection 提为顶层** `reflection/`（agent 元能力），不再在 intelligence/ 下。
- **三拆**：
  - 自进化引擎（run_reflection / generate_*_proposals / findings 生成）→ 留 agent 侧 `reflection/`。
  - 变更审批门（approve/reject/apply proposal）→ `governance/`（与 permission_gate 同类）。
  - 管理 API（list/get proposal、趋势查询）→ `platform/`。
- **自进化作用对象网络**：reflection 读 memory / knowledge_base.retrieval / trace，产出对 user-memory / shared-memory / KB / skill 的建议，经统一审批门落地（纲领 §4）。
- **依赖**：reflection → retrieval/memory（读）；✗→ ingest；写经 governance 审批门。

## Capabilities

### New Capabilities
<!-- 暂定，待讨论 -->

### Modified Capabilities
<!-- 待决策点定稿后写 -->

## Impact

- 拆分 `reflection.py`（1643 行）为跨 agent/governance/platform 三处。
- 调用方：`memory/shared.py`（apply_shared_memory_proposal）、`memory/trends.py`、`platform/skill_management/skill_admin_api.py`。
- 依赖阶段1（vector_store）、阶段2（KB retrieval 边界）就位更佳。

## 待讨论决策点（DRAFT — 明天讨论）

1. **1643 行的拆分粒度**：自进化引擎内部还细分吗（memory 反思 / KB 反思 / skill 机会各一块）？还是先按"引擎/审批门/管理API"三刀切，内部细分后置？
2. **审批门与 governance 现有抽象的关系**：`permission_gate`（运行时实时审批门）和 reflection 的"提案异步审批"是否共用一套审批抽象，还是 governance 下两个并列机制？
3. **管理 API 落 platform 哪里**：并入 `skill_management`（skill proposal 已在那），还是新建 `platform/reflection_management`（因为它还管 memory maintenance proposal、趋势）？
4. **shared-memory 提案落地链**（与阶段4 交叉）：`memory/shared.py:apply_shared_memory_proposal` 现在反向 import reflection。拆分后这条"reflection 生成提案 → 审批 → memory.shared 落地"的链怎么走，依赖方向如何摆正（避免 memory↔reflection 循环）。
5. **proposal/report 的存储归属**：`kb_reflection_reports` / `skill_proposals` / memory maintenance proposal 表——属 agent 侧（自进化产物）还是 platform（管理数据）？按判据应在 agent 侧，但审批状态字段偏治理。
6. **reflection 异步调度**：定时触发自进化由谁调度（cron_scheduler，platform 驱动）——与 KB connector sync 调度同属横切，是否一起设计。
