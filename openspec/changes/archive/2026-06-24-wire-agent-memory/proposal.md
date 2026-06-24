## Why

`agent_memory` 是个"零件造齐、两端没接线"的半成品（切片① `agent-memory-rescope` 明确把功能接通列为 OUT OF SCOPE，只做了正名 + agent 级 + 删 scope）：

- **写闭环断**：reflection 提案批准后 `mark_agent_memory_proposal_applied` 只标 `applied`，**不调 `create_agent_memory`**（全库零真实调用方）→ `agent_memory_items` 表永远空。这其实**违背已有 spec**——`self-evolution-split` 早已要求"审批门 resolve 后回调 agent memory 写接口落地"，是实现没跟上。
- **读闭环断**：`build_context`（long_term_ctx）只注入 user memory + KB，**不查 agent_memory** → 即使有记忆也用不上。

同时暴露一个存储遗留：`agent_memory_items` 单独住一个 `agent_memory.db`，而**同级姊妹 user memory（`memory_items`）早就在 `agent_state.db`**。独立库是切片① "scope 没想透时"留的尾巴；现 per-agent 定死，独立库理由消失。趁 agent_memory **当前空库零数据**，一并收编进 `agent_state.db`。

## What Changes

- **写闭环接通**：审批门 resolve 的 agent_memory 分支 → 调 `memory.create_agent_memory(type, content, created_by, source="reflection_proposal", source_ref=<proposal_id>)` 真落库 + 建向量索引，再标 applied。由 `governance` 编排（`governance → memory` 方向，符合 `self-evolution-split`），保 `memory ↛ reflection` 护栏。
- **读闭环接通**：`build_context` 新增 `search_agent_memory(query, limit)` 作**第三类源**（`source_type="agent_memory"`），与 user memory / KB 并列进候选选择。agent_memory 为 per-agent，检索**不传 user_id**。
- **读端预算独立第三档**：`LongTermContextSettings` 新增 `agent_memory_max_tokens` + `agent_memory_top_k`；`conflict_preference` 由 memory-vs-knowledge 两方扩为三方。
- **关系库收编**：`agent_memory_items` 表并入 `agent_state.db`（`CREATE TABLE` 进 `AGENT_STATE_MIGRATIONS` 新版本）；删 `memory/agent_memory_migrations.py`、`tenant_router` 的 `open_agent_memory_db`/`open_agent_memory_db_ro`/`AgentScope.agent_memory_db` 及 `resolve_agent` 里对 `agent_memory.db` 的 `create_substrate`；`agent_memory.py` 的 `set_agent_memory_db` 改用 `agent_state_db` 连接。**重建窗口、不搬数据**。
- **不动向量库**：`agent_memory_vectors.db` 保持独立。vector_store 按 family 路由（`mem`/`agentmem`/`shared`/`kb` 四个独立 family），`agentmem` family 有意分物理库；关系库与向量库本就分离，合关系库不要求合向量库。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `long-term-ctx`: 新增 agent_memory 作为第三类检索源 + 独立预算档（`agent_memory_max_tokens`/`top_k`）+ conflict_preference 三方。
- `self-evolution-split`: 强化——审批门 resolve agent_memory proposal 后**真写 `agent_memory_items`**（补一条可被守护的 scenario；spec 既有要求不变，钉死"落地=真增行"）。
- `agent-db-schema-self-init`: `agent_memory_items` 由独立 `agent_memory.db` 改为 `agent_state.db` 内（`AGENT_STATE_MIGRATIONS`）；不再创建 `agent_memory.db`。
- `tenant-scoped-db-routing`: `agent_scope` 移除 agent_memory **关系库** open/句柄（agent_memory 关系数据走 `agent_state.db`）；保留 agent_memory **向量** backend（`agentmem` family，独立向量库）。
- `platform-read-projection`: agent_memory 投影改为读 `agent_state.db`（per-agent，不再读独立 `agent_memory.db`）。

## Impact

- **owning packages**: `memory/`（`agent_memory.py` 写接口接通 + 删 `agent_memory_migrations.py`）、`long_term_ctx/`（读端第三源 + 预算）、`governance/`（`reflection_gate` 写端编排）。
- **public API surface**: `memory.create_agent_memory` 成为审批门落地调用点；`search_agent_memory(query, limit)` 成为 build_context 消费点；`set_agent_memory_db` 签名/接线改用 state_db。
- **owned tables**: `agent_memory_items` 从 `agent_memory.db` 迁入 `agent_state.db`（嵌入式 forward-only，新版本建表；旧独立库不再建）。
- **config namespace**: `LongTermContextSettings` 新增 `agent_memory_max_tokens` / `agent_memory_top_k`；`conflict_preference` 取值扩展。
- **cross-module dependencies**: 写端 `governance → memory`（合法方向）；`memory ↛ reflection`、agent 运行时 `↛ platform` 护栏须仍绿。
- **migration / shim plan**: 重建窗口，**不搬数据**（agent_memory 当前空）。`agent_memory.db` / `agent_memory_migrations.py` 直接退役，不留 shim。`runtime/agent_app._init_agent_db_schema` 接线改为 agent_memory 走 `agent_state_db`。
- **OUT OF SCOPE**: agent 主动写 agent_memory 的工具（MVP 只 reflection 提案源，主动写另开）；向量库合并（family router 不动）。
- 受影响代码：`memory/agent_memory.py`、`memory/agent_memory_migrations.py`(删)、`long_term_ctx/__init__.py`、`governance/reflection_gate.py`、`reflection/reflection.py`、`runtime/agent_state_migrations.py`、`runtime/agent_app.py`、`tenant_router.py`、`config.py`、`platform/read_projection.py`。
- **定位**：这是 agent_memory 三部曲收官——① `agent-memory-rescope`（正名+rescope，已落地）→ 本片（接通 + 关系库收编）。
