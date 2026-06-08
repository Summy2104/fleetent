## Context

`reflection.py`(1643, 2026-06-08 核对) 的函数按职责清晰分三组：

- **自进化引擎（agent 元能力）**：`run_reflection`、`run_kb_reflection_report`、`generate_memory_maintenance_proposals`、`generate_skill_proposals`、`_generate_findings`/`_generate_kb_findings`/`_memory_*_findings`/`_skill_opportunity_findings`/`_connector_findings`、`_read_memory_signals`。读 trace（observability）、memory、`knowledge_base`（顶 import `from fleetent.intelligence import knowledge_base, memory`）产出 finding + proposal。
- **变更审批门（governance）**：`approve/reject/expire_*_proposal`、`apply_skill_proposal`/`apply_memory_maintenance_proposal`、`mark_shared_memory_proposal_applied`、`apply_skill_proposal_to_boundary`、`_apply_maintenance_action`、`_auto_apply_allowed`、`_require_owner`/`_require_status`。
- **管理 API + 存储**：`get/list_skill_proposals`、`get/list_memory_maintenance_proposals`、`get_reflection_trend_summary` + 全部 `_trend_*`/`_aggregate_*`；存储 `_save_report`/`_save_kb_reflection_report`、proposal CRUD（`_insert/_update/_get/_*_params/_*_from_row`）。

跨域：`memory/shared.py:172`、`memory/trends.py:205` lazy-import reflection；`platform/skill_management/skill_admin_api.py` lazy-import reflection（`reflection_list_proposals`/`reflection_proposal_diff`，skill proposal 评审 inbox）。governance 现有：`permission_gate`（实时审批，asyncio.Event + approvals 表）、`agent_policy`、`audit_log`、`quota`、`blocklist`、`user_input_gate`。

约束：结构重构、行为零变更、测试全程绿；依赖阶段1/2/4；与阶段4 设计合并破循环。

## Goals / Non-Goals

**Goals:**
- reflection 三刀切：引擎（agent）/ 审批门（governance）/ 管理 API（platform/reflection_management）各归其位。
- proposal/report 存 agent 数据（自进化产物）。
- 审批门 = permission_gate 异步非阻塞泛化；resolve → 真相源写。
- 审批渠道按 proposal 类型路由。
- 破 memory↔reflection 循环（启用 `memory ✗→ reflection` 护栏）。

**Non-Goals:**
- 不改自进化算法 / finding 生成逻辑。
- **引擎内不再细分**（memory/KB/skill 反思暂留一块）——内部细分后置。
- 不实现 reflection 异步调度（cron，纲领 §9，重构后加）。
- 不改 `permission_gate` 本身契约。
- 不改 CLAUDE.md 契约文字（留阶段5）。

## Decisions

### D1：三刀切，引擎内不细分
`reflection.py` → 三处：

| 目标 | 内容 | 归属判据 |
| --- | --- | --- |
| `reflection/`（agent） | 引擎（run_*/generate_*/findings/_read_memory_signals）+ proposal/report 存储（CRUD/save） | §2.3 纵向元能力；§10 proposal 存 agent 数据 |
| `governance/reflection_gate.py` | approve/reject/expire/apply + `_apply_maintenance_action`/`_auto_apply_allowed`/`_require_*` | §2.2 审批是横切治理 |
| `platform/reflection_management/`（新建） | list/get proposal、趋势（trend/aggregate）、skill/KB console 评审暴露面 | §3 管理薄壳 |

引擎内部（memory 反思 / KB 反思 / skill 机会）**暂留一块**，不拆子模块——本阶段聚焦归位，内部细分风险大、收益低，后置。

### D2：proposal/report 存储留 agent `reflection/`
proposal/report 是自进化产物 = agent 数据（§10）。存储 helper（表 CRUD、save_report）留 agent `reflection/`（作 `reflection/store.py`）。门（governance）经此 store 改 proposal 状态；管理 API（platform）经此 store 读。依赖方向：governance → reflection.store；platform/reflection_management → reflection.store。二者都不被 reflection 引擎反依赖。

### D3：审批门 = permission_gate 的异步非阻塞泛化（governance 内并列）
`permission_gate` 是**实时**门（工具调用时 `asyncio.Event` 阻塞等 resolve）。reflection proposal 是**异步**门（proposal 持久化，延后经 IM/console resolve，不阻塞自进化）。二者**同类不同机制**，在 governance 下并列：新增 `governance/reflection_gate.py`（或 `proposal_gate`），承接 approve/reject/apply。`resolve()` 语义：

```
reflection 引擎 → 生成 proposal（存 reflection.store）
        ↓ (异步, 不阻塞)
governance proposal 门  ← 经渠道(IM/console) 收到 approve/reject
        ↓ resolve()
   回调真相源写接口落地:
     user/shared memory → memory.shared 写接口 (create/apply)
     skill              → skill 库写
     KB                 → agent-curated 沉淀源 (派生视图, 不直接写 KB)
```

- *替代*：复用同一 `PermissionGate` 类。否决——实时 vs 异步生命周期不同（前者进程内 Event、后者跨会话持久 proposal），强并会污染两者；同源泛化 + 并列更清晰。

### D4：审批渠道按 proposal 类型路由（§10）
门内按 proposal 类型选渠道：

| 类型 | 渠道 | 找谁 |
| --- | --- | --- |
| user memory | IM（agent 自主，`reply_func` 推送） | 该 user 本人 |
| shared memory | IM（agent 自主） | team/tenant 负责人（"找对人"逻辑见 Open Questions） |
| skill / KB | platform console（`list_*` 拉取） | 管理员 |

判据 = 影响范围：个人贴身·轻量·高频 → IM 自主；组织级·重 → platform 集中审。IM 路由全在 agent 侧（无 platform 依赖）；console 路由经 platform/reflection_management 暴露。

### D5：破 memory↔reflection 循环（与阶段4 合并）
方向正确的边：reflection 引擎 → memory / `knowledge_base.retrieval`（**读** trace/memory/KB 信号，§6 允许）。要断的反向边：
- `memory/shared.py` 移除 lazy-import reflection；`mark_shared_memory_proposal_applied` 迁到 reflection.store，由门调用；shared-memory proposal 落地由**门回调** `memory.shared.apply_shared_memory_proposal`（governance → memory.shared 写，方向正确）。
- `memory/trends.py` 的 reflection proposal 聚合迁到 `platform/reflection_management`（管理侧聚合）。
- 启用阶段4 标 TODO 的 `memory ✗→ reflection` 护栏。

### D6：skill proposal 管理迁 reflection_management
`skill_admin_api.reflection_list_proposals`/`reflection_proposal_diff`/apply（skill proposal 评审 inbox 的数据面）迁到 `platform/reflection_management`。`skill_management` 的评审 inbox UI 改为消费 reflection_management（行为不变）。skill_management 仍管 skill 上传/绑定等 skill 专属事务。

### D7：依赖护栏（本阶段加 reflection 边）
新增护栏断言：`reflection` ✗→ `knowledge_base.ingest`（自进化只读检索，不拉摄取）；`reflection` ✗→ `fleetent.platform`；`memory` ✗→ `reflection`（D5，启用阶段4 TODO）；`governance` ✗→ `platform`。

## Risks / Trade-offs

- **1643 行三处搬迁回归** → 纯移动 + 改 import，先固化现有 reflection 测试为基线；分目标搬迁后跑全量；shim 兜底旧路径。
- **门回调真相源的时序/事务** → 复用现有 `apply_*` 逻辑（仅换调用位置到 governance）；落地写仍走原真相源接口，事务边界不变。
- **审批渠道路由新增** → 路由按类型分支，IM/console 各复用既有推送/列表机制；测试覆盖每类型路由一次。
- **skill_management 消费方改动** → 经 reflection_management 间接消费，过渡期 skill_admin_api 可留薄 re-export；行为不变。
- **memory 写接口供门回调** → 阶段4 已把 memory.shared 写接口面定清楚，本阶段对接。
- **git 历史** → `git mv` / 拷贝保留可追溯。

## Migration Plan

1. `git mv` reflection.py → `reflection/`（引擎 + `reflection/store.py`）；旧路径 `intelligence/reflection.py` 留 re-export shim。
2. 抽审批门到 `governance/reflection_gate.py`（approve/reject/apply + resolve 回调真相源）；门经 reflection.store 改状态。
3. 新建 `platform/reflection_management/`（list/get/trend + skill/KB console 暴露面）；从 reflection.py 迁管理/聚合函数。
4. 门内实现按 proposal 类型路由（D4）。
5. 破循环（D5）：memory.shared / memory.trends 移除 reflection import；门回调 memory.shared 写；启用 `memory ✗→ reflection` 护栏。
6. 迁 skill_admin_api 的 proposal 管理面到 reflection_management（D6）。
7. 加 reflection 护栏断言（D7）。
8. 全量测试 + grep 无残留 + check_test_layers 绿。
9. 回滚 = 反向搬迁 + 删 shim；行为不变，回滚安全。

## Open Questions

- **shared-memory 审批"找对人"逻辑**：team/tenant 负责人如何确定（提案者≠审批者）。草案：由 scope（tenant_id/team_id）→ 负责人映射（owner 字段或 platform 用户角色查询）解析推送目标；本阶段先实现 user-memory IM 路由 + skill/KB console 路由，shared-memory "找对人" 留可注入的 resolver 接口，具体映射 apply 时定。
- **reflection 异步调度**（cron 定时触发自进化）：与 KB connector sync 调度同属横切（纲领 §9），归 platform 驱动，重构后单独加，本阶段不含。
- **引擎内细分**（memory/KB/skill 反思各一块）：后置，规则增多时再拆。
- shim 删除时机：本 change 末尾 vs 阶段5 统一收口——倾向阶段5。
