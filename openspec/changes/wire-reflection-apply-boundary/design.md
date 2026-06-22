## Context

reflection 审批链（agent 侧）当前结构：

- 提案存统一表 `reflection_proposals`（`domain` ∈ {memory, skill}、`kind` 区分动作），由 v24 引入。
  旧 per-type 表 `memory_maintenance_proposals`(v17)、`skill_proposals`(v19) 已在 v25/v26 DROP——**纯死表，不需再动**。
- `approval_router.resolve_approval_request` 按 `subject_type` 分派；`memory_proposal`/`skill_proposal`
  → `reflection_gate.resolve_reflection_proposal_action`。
- `reflection_gate` 内部按 `use_public_reflection_api = getattr(reflection_api, "_state_db", None) is not None`
  在两套实现间二选一：
  - **True**（agent 正常 boot，`set_state_db` 已接）→ 调 `reflection_api.*`（reflection.py 的真实现）。
  - **False**（fallback）→ 调 gate 本地的平行副本（基于 `store` 直访）。
- gate 本地平行副本里，memory 那套（`apply_memory_maintenance_proposal` 等）是**真实现**，唯独
  `apply_skill_proposal_to_boundary` 是 stub：`raise RuntimeError("skill proposal apply boundary is not configured")`。
- reflection.py 的 `apply_skill_proposal_to_boundary` 是**完整真实现**：`write_skill(...)` + `skill_registry.reload()`，
  覆盖 create/update/deprecate。

**何时触发 stub**：agent 进程内 resolve 时 `_state_db` 已接 → 走真 API，不触发。stub 只在 `_state_db` 未接的 fallback
路径触发——典型是**平台进程**（agent 侧 reflection state_db 不在平台进程接线）去 resolve agent 提案时。这条平台 resolve
路径本身是 A3 要清理的对象；本切片不改它的存在性，只把 stub 接到真实现，消除"必崩"。

## Goals / Non-Goals

**Goals:**
- 消除 skill 提案批准 → RuntimeError 的 landmine：gate 的 apply 边界委托到 reflection.py 真实现（单一真相源）。
- dataclass `MemoryMaintenanceProposal → MemoryProposal` 全量改名，与 `SkillProposal` 对齐。
- 修正 `skill-proposal-review` spec 的死表引用，并把"approved skill 提案经边界应用"显式写进 spec。

**Non-Goals:**
- 不移除 gate 的 fallback 平行副本整体（改跨进程语义 → A3）。
- 不接 `AutoMaintenancePolicy` / auto-apply（A2）。
- 不改 approver 找对人规则（A4）。
- 不新增/不改任何迁移（死表已 DROP，无 schema 变动）。

## Decisions

**D1 · apply 边界委托而非复制**：reflection_gate 的本地
`async def apply_skill_proposal_to_boundary(proposal)` 改为
`await reflection_api.apply_skill_proposal_to_boundary(proposal)`，删掉 `raise` 占位。
保留 gate 本地的 `apply_skill_proposal` 包装（status 流转 + `store._update_skill_proposal`），只把"实际落地动作"
这一处委托出去。这样无论走真 API 还是 fallback，apply 动作都用同一份真实现（write_skill + reload），杜绝漂移。
（不直接在 fallback 里整体调 `reflection_api.apply_skill_proposal`，因 fallback 的存在本就是为 `_state_db` 未接场景，
其 status 持久化走 gate 的 `store`；只替换最内层的 boundary 调用，改动面最小、语义最稳。）

**D2 · dataclass 纯改名**：`MemoryMaintenanceProposal → MemoryProposal`，一次性替换 10 个文件
（`reflection/reflection.py`、`reflection/store.py`、`governance/reflection_gate.py`、`memory/proposal_store.py`
+ 5 个单测 + 1 个集成测试）。字段、`reflection_proposals` 行结构、序列化均不变（DB 不存类名）。**不保留旧名 alias**——
内部 dataclass，无外部 import 契约；保留 alias 反而留下二次清理债。

**D3 · spec delta（skill-proposal-review）**：
- 修正 "Proposal inbox" 需求：来源 `skill_proposals` → `reflection_proposals`（`domain='skill'`，pending）。
- 新增 "Skill proposal application" 需求：approved 状态的 skill 提案被 resolve 为 apply 时，SHALL 经 skill 管理边界
  （`write_skill` + registry reload）真正落地；不得停在未配置 stub。这条把之前无规格覆盖的行为显式化，防止 stub 复活。

## Risks / Trade-offs

- **fallback 路径在平台进程仍不完全正确**：即便 boundary 接到真实现，`write_skill`/`skill_registry` 是 agent 侧能力，
  平台进程未必有 agent 的 skill 目录。本切片只保证"不再 RuntimeError + agent 进程内正确"；平台 resolve 该不该存在留给 A3。
  这是有意的范围切割，避免 A1 隐含 A3 决策。
- **改名波及面（10 文件）**：机械但广。靠 TDD 红/绿 + 全量 reflection/gate 单测兜底；改名后 `grep -rn MemoryMaintenanceProposal`
  必须为空（含字符串/注释残留）。
- **测试覆盖 stub 修复**：需新增/调整一个测试，断言"`_state_db` 未接（fallback）路径下 apply skill 提案不再 raise stub、
  而是调用到真实 boundary"——否则改动可能被现有只覆盖真 API 路径的测试漏掉。
