## Context

共享记忆有 agent 侧治理生命周期(reflection 提议→审批门→`apply_shared_memory_proposal`→`create_shared_memory(source="reflection_proposal")`)。两个平台侧手动入口(CLI + 我加的 HTTP API)调 `create_shared_memory(source="manual")` 绕过它,且放错了层。审查确认无 UI 消费该 API。

注意:这与「KB 由平台 admin 管理」不矛盾——KB 没有 agent 侧提议/审批生命周期,平台管理是其设计;共享记忆有,所以平台直写是越权旁路。

## Goals / Non-Goals

**Goals:** 撤 CLI + HTTP 两个平台侧手动入口;回收/强化 spec;共享记忆回到纯 agent 侧。

**Non-Goals:** 不碰 `memory.shared` 数据层与 reflection proposal/apply 生命周期(agent 侧、正确);不新增 agent 侧手动编辑能力(后续另议);不动 KB / observability 等平台合法读/管理面。

## Decisions

### D1:两个平台侧入口都删,不是二选一

不同于租户(管理库、CLI vs HTTP 二选一),共享记忆是 agent 侧数据 + 有 agent 侧治理。**CLI 和我的 HTTP API 都在平台侧、都绕过治理**,两个都撤。删 `shared_memory_management/` 整包 + `admin_cli/shared_memory.py`。

### D2:spec 落点——强化已有要求,不新造原则

「Shared Memory edits use proposal lifecycle」已在 `manual-maintenance-entrypoints`。原措辞限定"this maintenance surface"。MODIFY 为:**任何平台面(maintenance / 专用 CLI / HTTP API)均不提供共享记忆直写**,改动走 agent 侧 proposal/apply。比新造 module-boundaries 原则更准——因为 KB 等其他 agent 侧数据仍有合法平台管理面,不能一刀切"平台不碰 agent 侧数据"。

### D3:数据层与测试边界

`memory.shared`(create/update/archive/list 函数)**保留**——它是 reflection 生命周期落地的底层原语(`apply_shared_memory_proposal` 仍调 `create_shared_memory(source="reflection_proposal")`)。只删**平台侧消费方**(CLI/HTTP)。`test_coverage_memory_and_platform_logic.py` 测数据层,保留。

### D4:文档同步

`docs/roadmaps/intelligence-roadmap*.md` 引用 `memory shared` CLI 的地方改为"经 reflection proposal/apply 生命周期";`test_deployment_docs.py::test_intelligence_roadmap_manual_uses_current_shared_memory_cli` 改为不再断言 CLI 存在(断言文档不再把已删 CLI 列为当前入口)。

## Risks / Trade-offs

- **[手动编辑能力暂缺]** 撤入口后,主动手工写一条共享记忆无平台路径,只能靠 reflection 提议。→ 这是有意的:共享记忆改动应走治理;若确需主动手动编辑,作为 agent 侧 change 另建,不在平台开旁路。
- **[回退既有 API]** 回退 complete-admin-api-coverage / align 中共享记忆部分。→ 无 UI 依赖、仅测试 + wiring,回退干净。
- **[manual-maintenance spec 扩面]** 把要求从维护面扩到全平台面。→ 与该 capability 的治理意图一致,非范围漂移。
