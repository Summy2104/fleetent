> **状态：DRAFT — 待 Randy 讨论修订**。物理移动部分把握较大；shared 控制面剥离含未决点（见末尾）。design/tasks 待讨论后补。

## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段4**。解散 intelligence/ 的收尾：把 `memory`（agent 记忆，核心健康）和 `long_term_ctx`（上下文聚合，取独立顶层方案 A）提为顶层；同时把 shared-memory 的人工录入/审批 API 收到 platform 薄壳，能力本体留 agent 侧。

## What Changes（轮廓，细节待讨论）

- **memory 提为顶层** `memory/`（agent 能力：提取/检索/自维护/shared 核心），`store` 作为域内 core。
- **long_term_ctx 提为顶层** `long_term_ctx/`（含 `_policy`），对话内被 runtime 调用聚合 memory + knowledge_base.retrieval。
- **shared-memory 控制面剥离**：人工录入（`source="manual"`）+ admin audit 的 API → platform 薄壳；变更审批门 → governance；shared-memory 的检索/被注入/自进化提案落地（`source="reflection_proposal"`）留 agent 侧。
- **依赖**：long_term_ctx → memory + knowledge_base.retrieval + vector_store；memory → vector_store + 域内 store。

## Capabilities

### New Capabilities
<!-- 暂定，待讨论 -->

### Modified Capabilities
<!-- 待决策点定稿后写 -->

## Impact

- 物理移动 memory / long_term_ctx 到顶层 + shim。
- 调用方：`runtime/loop`（memory extraction + long_term_ctx 构建上下文）、`admin_cli/shared_memory`（platform）。
- 依赖阶段1（vector_store）、与阶段3（reflection 拆分）在 shared-memory 提案链上交叉。

## 待讨论决策点（DRAFT — 明天讨论）

1. **shared-memory 哪些算"控制面薄壳"**：`create/update/archive_shared_memory`（manual 入口）+ `record_shared_memory_admin_audit` 归 platform？而 `search_shared_memory` / `apply_shared_memory_proposal`（reflection 落地）留 agent？边界要逐个函数定。
2. **long_term_ctx 取 A 的落地**：独立顶层 `long_term_ctx/`，被 runtime 依赖——确认它不并入 runtime（已定 A，此处仅落地确认）。
3. **memory store 作为域内 core**：是否和 KB core 一样显式分读写接口？还是 memory 写都是 agent 自然产生（无外部摄取）、不需要那么强的读写分离？
4. **memory 与 reflection 的循环**（与阶段3 交叉）：`memory/shared.py` 现反向 import reflection 做 apply_proposal。拆分后依赖方向怎么摆（建议：审批门在 governance 居中，memory 与 reflection 都不直接依赖对方）。
5. **shared-memory 的 namespace/scope**（tenant/team）治理：tenant_shared / team_shared 的可见性控制属 agent 检索逻辑还是 platform 治理。
