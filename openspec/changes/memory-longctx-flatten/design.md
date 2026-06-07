## Context

memory 现状（2026-06-08 核对）：`intelligence/memory/` 8 文件——`extraction.py`(268)、`search.py`(29)、`maintenance.py`(65)、`operations.py`(81)、`models.py`(77)、`store.py`(300)、`shared.py`(378)、`trends.py`(235)。`__init__.py` re-export 各子模块公共符号。

long_term_ctx 现状：`long_term_ctx.py`(582) 顶 import `knowledge_base`、`long_term_ctx_policy`、`memory`；`long_term_ctx_policy.py`(306) 读写 `long_term_context_policies` 表（agent 侧 policy）。调用方 `runtime/loop.py`、`agent_config.py`。

跨域耦合：`memory/shared.py:172` 与 `memory/trends.py:205` **函数内 lazy import** `from fleetent.intelligence import reflection`；`reflection.py` 顶 import `memory`/`knowledge_base`——构成 memory↔reflection 循环。`record_shared_memory_admin_audit` 在 `memory/shared.py`（agent），由 `admin_cli/shared_memory.py`（platform）调用。

约束：结构重构、行为零变更、测试全程绿；沿用 roadmap Shim 策略；依赖阶段1（vector_store）、阶段2（KB retrieval）；在阶段3 前实施。

## Goals / Non-Goals

**Goals:**
- memory / long_term_ctx 提为顶层，定位一致。
- long_term_ctx 取方案 A——**独立顶层包**（含 `_policy`），被 runtime 依赖，不并入 runtime。
- shared-memory 控制面薄壳（审计）归 platform，能力本体留 agent。
- 为阶段3 的审批门破环铺路：把 memory.shared 的写接口面定清楚。

**Non-Goals:**
- 不改记忆提取/检索/维护算法、不改 policy 语义。
- 不在本阶段拆 reflection（阶段3）；本阶段保留 memory→reflection lazy-import（经 shim）。
- 不给 memory store 上 Readable/Writable Protocol（见 D3）。
- 不改 CLAUDE.md 契约文字（留阶段5）。

## Decisions

### D1：memory 整体提为顶层 `memory/`
`git mv intelligence/memory/ memory/`，旧路径 `intelligence/memory/__init__.py` 留 re-export shim。内部相对 import 改顶层。`store` 留作域内 core。

### D2：long_term_ctx 取方案 A——独立顶层包（含 `_policy`）
`long_term_ctx.py` → `long_term_ctx/__init__.py`；`long_term_ctx_policy.py` → `long_term_ctx/_policy.py`。它是**跨域聚合者**（依赖 memory + knowledge_base.retrieval），与 memory 平级在顶层，其"更高层"由依赖方向表达（被 runtime 调、不被能力域反依赖），**不并入 runtime**——保持 runtime 薄、聚合逻辑可独立测试。

- *替代*：并入 `runtime/`。否决——聚合策略（policy + 注入）是独立关注点，混进 runtime 会让 runtime 变胖且耦合 memory/KB。

### D3：memory store 不强制读写分离（与 KB 不对称）
KB 有外部摄取（ingest）这个**外部写边界**，故需 Readable/Writable 隔离。memory 的写**全是 agent 对话自然产生**（extraction / maintenance / shared apply），无外部摄取、无 platform 驱动写——不存在"读边界不该拿到写"的隔离需求。故 memory `store` 保持**单一接口**，依赖约束靠护栏（memory ✗→ long_term_ctx/reflection、组件 ✗→ platform）表达即可。对称上 Protocol 属过度设计。

### D4：shared-memory 控制面薄壳——只剥审计
逐函数判定 `memory/shared.py`：

| 函数 | 归属 | 理由 |
| --- | --- | --- |
| `create/update/archive_shared_memory`、`_insert/_update/_new_item/_sync_vector` | agent（memory.shared 核心） | 写本体，manual 与 reflection_proposal 两源共用 |
| `search_shared_memory`、`iter_indexable_shared_memories`、`get/list_shared_memory` | agent | 检索/被注入（对话期经 long_term_ctx） |
| `apply_shared_memory_proposal` | agent | reflection 提案落地的写接口（阶段3 的门调用它） |
| `record_shared_memory_admin_audit` | **platform 薄壳** | 写治理审计，是管理暴露面 |

manual 录入的**入口编排**已在 `admin_cli/shared_memory.py`（platform）——它是天然的薄壳，调用 agent 侧核心写。本阶段只把**审计记录**迁到 platform 侧，核心写留 agent。判据 2：能力本体留 agent，管理/审计是 platform 薄暴露面。

### D5：memory↔reflection 循环——本阶段铺路，阶段3 断
目标依赖方向：memory ✗→ reflection，审批门在 governance 居中（reflection 生成提案 → 门 → 回调 memory.shared 写接口）。但 governance 审批门在阶段3 才建。本阶段：
- 保留 `memory/shared.py`、`memory/trends.py` 的 lazy-import reflection（经 shim 仍可用，二者均 agent 侧，非 platform 违规）。
- **明确 memory.shared 的写接口面**（`apply_shared_memory_proposal` / `create_shared_memory`）作为阶段3 门的回调目标，并在 spec 标注"阶段3 落地后 memory ✗→ reflection 由护栏强制"。
- trends 对 reflection proposal 的聚合（`trends.py:205`）随阶段3 管理 API（platform/reflection_management）归位。

- *替代*：本阶段就强行断环。否决——门未建，断了 apply 链会破坏 reflection_proposal 落地；3/4 设计合并、按序落地最稳。

### D6：依赖护栏渐进上（本阶段加 memory/long_term_ctx 边）
新增护栏断言：`memory` ✗→ `long_term_ctx`（能力域不反依赖聚合者）；`memory` / `long_term_ctx` ✗→ `fleetent.platform`。`memory ✗→ reflection` 留阶段3 门落地后启用（本阶段标注 TODO，不强制）。

## Risks / Trade-offs

- **lazy-import 经 shim 的脆弱性** → 阶段3 紧接断环；本阶段全量测试守 memory/reflection 协作不回归。
- **long_term_ctx 包化改 import 面** → 调用方 `runtime/loop`、`agent_config` 改 `long_term_ctx`（包）；公共符号经 `__init__` re-export，调用方零语义改动。
- **审计剥离改 admin_cli** → 审计写迁 platform，行为不变（同一张审计表）；用集成测试守。
- **policy 表迁移** → `_policy` 仅改 import 路径，表名/SQL 不变。
- **git 历史** → `git mv` 保留。

## Migration Plan

1. `git mv intelligence/memory/ memory/`；旧路径留 shim；修内部 import。
2. `git mv` long_term_ctx 两文件 → `long_term_ctx/{__init__,_policy}.py`；旧路径留 shim。
3. memory.shared 审计记录迁 platform 薄壳（D4）；admin_cli 调整。
4. 迁调用方：`runtime/loop`、`agent_config` → 顶层 `memory` / `long_term_ctx`。
5. 加 memory/long_term_ctx 护栏断言（D6）；`memory ✗→ reflection` 标 TODO（阶段3 启用）。
6. 全量测试 + grep 无残留 + check_test_layers 绿。
7. 回滚 = 反向 `git mv` + 删 shim；行为不变，回滚安全。

## Open Questions

- shared-memory 的 tenant/team scope 可见性控制——属 agent 检索逻辑（留 agent），本阶段不动；阶段6 服务化时若需平台级治理再议。
- `apply_shared_memory_proposal` 的 actor 校验在阶段3 门接管后是否仍需 memory 侧保留——阶段3 设计时定。
- shim 删除时机：本 change 末尾 vs 阶段5 统一收口——倾向阶段5。
