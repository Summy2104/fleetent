## Why

reflection 审批链的 skill 分支有一个潜伏 bug + 一处命名/规格陈旧：

1. **skill 提案批准后会 RuntimeError（潜伏 landmine）**：`governance/reflection_gate.py` 里本地的
   `apply_skill_proposal_to_boundary` 是一个 `raise RuntimeError("skill proposal apply boundary is not configured")`
   占位 stub。reflection_gate 按 `use_public_reflection_api`（= `reflection_api._state_db is not None`）二选一：
   agent 正常 boot 接了 `set_state_db` 时走 `reflection_api` 的真实现（OK），但 `_state_db` 未接线的 fallback 路径
   走本地 stub → skill 提案一旦批准就崩。`reflection/reflection.py` 已有完整真实现
   （`apply_skill_proposal_to_boundary`：`write_skill` + `skill_registry.reload`），但 gate 的本地副本没接到它。

2. **spec 引用死表**：`skill-proposal-review` spec 仍写"从 `skill_proposals` 聚合 inbox"，但 `skill_proposals`
   已在 agent_state 迁移 v26 被 DROP，真实存储是统一表 `reflection_proposals`（`domain='skill'`）。spec 与实现脱节。

3. **dataclass 命名冗长**：`MemoryProposal` 与同族的 `SkillProposal` 不对齐，旧名里的 "Maintenance" 中缀冗余。

现在做：这些是 reflection 审批链收尾的纯清理 + bug 修，不依赖任何待定决策（auto-apply 默认值、找对人规则均属后续切片），
可独立先落地，解除 skill 提案应用这条路上的 landmine。

## What Changes

- **接通 skill apply 边界**：reflection_gate 本地 `apply_skill_proposal_to_boundary` 不再 raise stub，改为**委托到
  `reflection_api.apply_skill_proposal_to_boundary`**（reflection.py 的真实现，单一真相源）。两条路径（真 API / fallback）
  都能正确应用 skill 提案。
- **dataclass 改名** `MemoryProposal`：贯穿 `reflection/`、`governance/`、`memory/`
  及测试（10 个文件），与 `SkillProposal` 命名对齐。纯重命名，不改字段、不改持久化（DB 存的是 `reflection_proposals`
  行的 `domain/kind`，不含类名）。
- **修正 spec 陈旧引用**：`skill-proposal-review` inbox 来源从死表 `skill_proposals` 更正为
  `reflection_proposals`（`domain='skill'`）；补一条"approved skill 提案 SHALL 经 skill 管理边界应用"的需求，
  把这条之前无规格覆盖（故 stub 得以存在）的行为显式化。

**明确不做（属相邻切片，避免踩界）**：
- 不删 reflection_gate 的整套 fallback 平行副本——完整移除会改变"平台进程 resolve agent 提案"的跨进程语义，
  属 **A3（平台只读投影 / 收窄 platform resolve）**，本切片只把 skill boundary 这一处 stub 接到真实现。
- 不接 `AutoMaintenancePolicy`（auto-apply）——属 **A2**。
- 不动找对人 approver 规则——属 **A4**。
- 死表已由 v25/v26 DROP，**不新增迁移**。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `skill-proposal-review`: 修正 inbox 数据来源（`skill_proposals` 死表 → `reflection_proposals` domain='skill'）；
  新增"approved skill 提案经 skill 管理边界应用（write_skill + registry reload）"的需求。

## Impact

- **owning package**：`reflection/`（真实现所在）、`governance/`（reflection_gate 委托）
- **public API surface**：`reflection.apply_skill_proposal_to_boundary`（已存在，本切片让 gate 复用它）；
  `MemoryProposal`（重命名后的 dataclass，跨 `reflection`/`governance`/`memory` 引用）
- **owned tables**：`reflection_proposals`（无 schema 改动）；死表 `memory_maintenance_proposals`/`skill_proposals` 已 DROP，不触碰
- **config namespace**：无
- **cross-module dependencies**：`governance.reflection_gate` 已 import `reflection.reflection`（既有方向，不新增契约）；
  无 agent→platform 反向依赖
- **migration / shim**：无迁移。dataclass 重命名为纯改名——如有跨模块旧引用风险，apply 时一次性全量替换，不保留旧名 alias
  （内部 dataclass、无外部 import 契约）
- **受影响代码**：`src/fleetent/governance/reflection_gate.py`、`src/fleetent/reflection/reflection.py`、
  `src/fleetent/reflection/store.py`、`src/fleetent/memory/proposal_store.py` + 5 个 reflection/gate 单测、1 个集成测试
