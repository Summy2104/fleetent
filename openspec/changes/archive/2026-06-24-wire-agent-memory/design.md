## Context

`agent_memory` 经切片① `agent-memory-rescope` 完成正名 + agent 级 + 删 scope，但功能未接通（切片①明确 OUT OF SCOPE）：

- **写**：`reflection.mark_agent_memory_proposal_applied` 只 `_with_status(proposal,"applied")`，不调 `create_agent_memory`（全库零真实调用方）→ `agent_memory_items` 永远空。这违背 `self-evolution-split` spec（已要求"审批门 resolve 回调写接口落地"）。
- **读**：`long_term_ctx.build_context` 只取 `memory.search`（user memory）+ `_search_knowledge`（KB），不查 `search_agent_memory`。
- **存储遗留**：`agent_memory_items` 独居 `agent_memory.db`，而 user memory（`memory_items`）早在 `agent_state.db`——独立库是切片①"scope 未定时"的尾巴。

底层已就绪：`agent_app._init_agent_db_schema`（boot）已 `open_agent_memory_db` + `set_agent_memory_db`，`create_agent_memory`/`search_agent_memory` 运行时可用；只是无人调。

约束：`memory ↛ reflection`、agent 运行时 `↛ platform`（CI 护栏）；`governance` 可 import 两侧（编排合法）。

## Goals / Non-Goals

**Goals:**
- 写闭环：审批门 resolve agent_memory proposal → 真 `create_agent_memory` 落库 + 索引。
- 读闭环：`build_context` 加 agent_memory 第三源 + 独立预算档。
- 关系库收编：`agent_memory_items` 并入 `agent_state.db`，退役 `agent_memory.db`。

**Non-Goals:**
- agent 主动写 agent_memory 的工具（MVP 只 reflection 源）。
- 向量库合并（`agentmem` family 保持独立向量库）。
- 数据搬迁（agent_memory 当前空，重建窗口）。

## Decisions

### D1 — 写端：governance 编排，apply 真写

审批门 resolve 的 agent_memory 分支：调 `memory.create_agent_memory(type, content=proposal.proposed_content, created_by=<reviewer/owner>, source="reflection_proposal", source_ref=proposal_id)` → 再标 applied。
- 位置：`governance/reflection_gate`（可 import memory + reflection，方向 `governance → memory` 合法），不让 memory import reflection。
- `mark_agent_memory_proposal_applied` 从"只标 applied"改为"先写库再标 applied"，或由 gate 编排两步。type 取 `metadata_patch` 的 type（缺则默认 `context`）。

### D2 — 读端：第三类源 + 独立预算档（explore D2=A）

`build_context` 增 `search_agent_memory(query, _AGENT_MEMORY_LIMIT)` → `agent_memory_candidates`（`source_type="agent_memory"`）→ 并入 `_ordered_candidates` / `_select_candidates`。
- `_select_candidates` 的二元 `source_type=="memory" else knowledge` 改三元：memory / agent_memory / knowledge 各自 `*_max_tokens` + `*_top_k`。
- `LongTermContextSettings` 增 `agent_memory_max_tokens` / `agent_memory_top_k`；`conflict_preference` 扩三方（默认值保证向后兼容：agent_memory 缺省给合理小预算）。
- agent_memory per-agent：`search_agent_memory(query, limit)` 无 user_id 参数，build_context 这一路不传 user_id（D4）。

### D3 — 关系库收编：agent_memory_items → agent_state.db

- `AGENT_STATE_MIGRATIONS` 加新版本：`CREATE TABLE agent_memory_items (...)`（沿用 `agent_memory_migrations` 的列，无 scope 列）。
- 删 `memory/agent_memory_migrations.py`；`tenant_router`：删 `open_agent_memory_db`/`open_agent_memory_db_ro`、`AgentScope.agent_memory_db`、`resolve_agent` 里 `agent_memory.db` 的 `create_substrate`（**保留** `agent_memory_vector_backend`，agentmem 向量库不动）。
- `memory/agent_memory.py`：`set_agent_memory_db(db, vector_backend)` 的 `db` 改为传入 `agent_state_db`（关系操作走 state 库）；向量仍用注入的 agentmem backend。
- `agent_app._init_agent_db_schema`：agent_memory 关系不再 `open_agent_memory_db`，改用已 open 的 `state_db`；向量 backend 仍接 agentmem。
- `platform/read_projection`：agent_memory 投影读 `agent_state.db` 的 `agent_memory_items`（只读不迁移句柄）。

### D4 — 向量库不动

`agent_memory_vectors.db`（`agentmem` family）保持独立。vector_store family router 一 family 一物理库的设计不改；关系库与向量库本就分离，收编关系库不触碰向量层。

## Risks / Trade-offs

- **[读端预算回归]** → 三方拆分要保证既有 memory/knowledge 行为不变（agent_memory 缺省预算不挤占）；用 long-term-ctx 既有 evaluation fixtures + 新增 agent_memory 用例守护。
- **[写端 type 缺失]** → proposal 无明确 type 时默认 `context`，不阻断 apply。
- **[收编动 schema]** → `agent_memory_items` 进 `AGENT_STATE_MIGRATIONS` 新版本；重建窗口不搬旧 `agent_memory.db` 数据（空库）。旧库文件残留无害（不再创建/读取）。
- **[护栏]** → 写端经 governance 编排，`memory ↛ reflection` 不破；跑 `test_module_dependency_guardrails`。
- **[platform 投影]** → 切片①改成读独立 agent_memory.db，本片再改读 agent_state.db；确保投影测试同步。

## Migration Plan

1. `AGENT_STATE_MIGRATIONS` 加 `agent_memory_items` 建表版本。
2. 接线改 agent_memory 关系走 state_db；删 tenant_router/agent_memory_migrations 的独立库路径。
3. 写端 + 读端接通。
4. 重建 dev/test 环境验证（不搬数据）。旧 `agent_memory.db` 若存在则忽略（可手动删，无逻辑依赖）。
5. 回滚：恢复独立库路径 + 摘除 build_context/gate 调用即可。

## Open Questions

- `conflict_preference` 三方的默认取向（建议默认 `auto`：相关性分数优先，agent_memory 与 user memory 同权、KB 次之）——apply 时定默认值并加 fixture。
- agent_memory 在 prompt 里的区段标题/渲染（与 `[Long-term context]` 下 memory/knowledge 区段并列；`_render_context` 加 agent_memory 区）。
