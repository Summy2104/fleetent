# 设计 — agent-dual-state-gating

## Context

控制台 agent 查询与启停逻辑现状（2026-06-23 审计，worktree `feat/agent-dual-state-gating`）：

- `src/fleetent/platform/agent_management_console/agent_console_api.py`
  - `list_agents`（L207–220）：返回 `agent_admin_store.list_states()` 行（含 `agent_id` / `agent_name` / `status` / `provenance` / `drift` / `is_default` / …）+ 最佳努力 `icon`。
  - `_def_response`（L234–266）：详情体；agent 存在时 `agent_admin_store.get_state(agent_id)` 取期望态，仅暴露 `status` / `provenance`。
  - `create_agent`（L328–355）：建 def 后 `set_provenance(adhoc)` + **`enable(agent_id)`**（L353）。
  - `clone_agent`（L473–497）：建 def 后 `set_provenance(adhoc)` + **`enable(agent_id)`**（L495）。
  - `enable_agent`（L430–435）：仅 `_require_admin` + `agent_admin_store.enable`，**无 node 绑定守卫**。
  - 该文件**未** import `node_store` / `placement_store`；跨模块读取用模块级**注入 seam**（`get_agent_def` / `create_agent_def` / …，由 `server.py` `wire_agent_store_seams` 接线，测试 monkeypatch）。
- `src/fleetent/platform/node_management/node_store.py`：有 `upsert_agent_status`（写）、`list_agent_status_by_node(node_id)`（读），**无** `get_agent_status(agent_id)`。`node_agent_status` 列：`agent_id`(唯一/PK) / `node_id` / `phase` / `pid` / `health` / `detail` / `reported_at`。
- `src/fleetent/platform/node_management/placement_store.py`：`get_for_agent(agent_id) -> dict | None`（返回 `{agent_id, node_id, pinned_at, pinned_by, updated_at}`）已存在；无 `list_placements()`。
- `src/fleetent/server.py` `wire_agent_store_seams`（L466+）：集中接线 console seam；`placement_store` 已在 server 直接 import（`_resolve_agent_node_id`）。
- 前端 `frontend/src/features/agents/`：`page.tsx` `formatStatus`（L74–80）只输出 `[status]`(+`default`)，Enable/Disable 按钮按 `agent.status === 'disabled'` 切换、无 `disabled` 属性；`api.ts` `AgentListItem` / `AgentDetail` 只有 `status` / `provenance` 字符串字段。测试 Vitest + jsdom + MSW（`onUnhandledRequest: 'error'`）。

跨能力一致性：`node-desired-state-api` 的「分区期望态拉取」已按 `agent_admin_state.status == "enabled"` 过滤——这是 status「第一次真正生效」的接线点。本 change 与之组合：新建默认 `disabled` + enable 需绑定 node ⇒ agent 只有真正 pin 到 node 后才能 enabled，才会被该 node 拉起，期望态与可运行性从源头一致。

## Goals / Non-Goals

**Goals**
- 控制台列表/详情一处呈现期望态 + 运行态 + 绑定，不破坏既有响应字段。
- 新建/克隆默认 `disabled`，杜绝「enabled 但无处可跑」的误导态。
- enable 收紧为「已绑定 node 才允许」，否则 409。
- 前端双态展示 + 未绑定时禁用 Enable 并解释原因。

**Non-Goals**
- 不改 agent 运行时、不改 `agent_config.py`、不改 node 上报写入路径（`upsert_agent_status` 不动）。
- 不改 `restore` 语义（仍直接置 enabled，不加 node 守卫）——避免无法恢复已归档 agent。
- 不动 `get_state` 无记录时的 `enabled` 回退默认（仅影响完全无 admin_state 行的 agent，超范围且有回归风险）。
- 不新增持久化表、不做 schema 迁移。
- 不引入实时推送/轮询机制；运行态新鲜度沿用 node 上报频率（`reported_at` 透出供前端判断陈旧）。

## Decisions

**D1 · 注入 seam 而非直接 import**
`agent_console_api` 经新增模块级 seam 读取运行态/绑定，而非直接 `import node_store/placement_store`：

- `get_agent_runtime(agent_id) -> dict | None`（详情）→ 接线 `node_store.get_agent_status`
- `get_agent_placement(agent_id) -> dict | None`（详情 + enable 守卫）→ 接线 `placement_store.get_for_agent`
- `list_agent_runtimes() -> list[dict]`（列表批量）→ 接线 `node_store.list_agent_status`
- `list_agent_placements() -> list[dict]`（列表批量）→ 接线 `placement_store.list_placements`

理由：(a) 与该文件既有 seam 哲学一致（`get_agent_def` 等都走 seam）；(b) **unit 测试可 mock 而不碰真实 DB**——既有 `tests/unit/test_coverage_admin_connector_handlers.py` 直接调 `enable_agent`，若直接 import 真实 store 会击穿 DB、违反 unit 分层；(c) 默认实现为 no-op（返回 `None` / `[]`），未接线时退化为「只有期望态」，不崩。

**D2 · 列表用批量 seam、详情/守卫用单条 seam（避免 N+1）**
列表对 N 个 agent 若逐行查 runtime/placement 即 N+1。改为：列表调 `list_agent_runtimes()` + `list_agent_placements()` 各一次，在内存按 `agent_id` 构 map 后 join（共 3 次查询：states + statuses + placements）。详情与 enable 守卫只针对单 agent，用单条 seam。

**D3 · 响应字段形态**
- `runtime`：有 `node_agent_status` 行时为 `{phase, health, pid, node_id, reported_at}`，无行为 `null`。
- `placement`：有 `agent_placements` 行时为 `{node_id, pinned_at, pinned_by}`，未 pin 为 `null`。
- 既有顶层字段（`status` / `provenance` / `agent_name` / `icon` / 详情的 def 字段等）原样保留。前端「是否已绑定」= `placement !== null`；「是否在跑」= `runtime?.phase === 'running'`，无需额外派生字段。

**D4 · 默认 disabled 的落点**
仅改 `create_agent`（L353）与 `clone_agent`（L495）由 `agent_admin_store.enable` 改 `agent_admin_store.disable`。`agent_admin_store` 自身的 `enable`/默认回退不动——默认策略属「控制台创建语义」，留在 API 层，store 保持中立。

**D5 · enable 守卫的位置与错误码**
守卫放在 `enable_agent` 端点（HTTP 层），`_require_admin` 之后、`agent_admin_store.enable` 之前：`get_agent_placement(agent_id)` 为 `None` ⇒ `HTTPException(409, "agent not bound to a node")`，不写状态、不写 `agent.enable` 审计。选 409（冲突/前置条件不满足）而非 422，与既有 archive 绑定保护用 409 一致。`disable` 不加守卫（停用永远允许）。

**D6 · 前端 gating 用 disable + 提示而非隐藏**
未绑定 node 时 Enable 控件 `disabled` 并附原因提示（如 `title` / 辅助文字），而非隐藏。理由：可发现性——管理员看到按钮存在但被禁用 + 原因，比按钮凭空消失更易理解下一步（先去 pin node）。运行态展示在卡片上以 `status` + `runtime` 两段呈现。

## Risks / Trade-offs

- **既有测试随契约变更需同步更新**（属预期，非「新增失败」）：
  - `tests/integration/test_agent_console_api.py::test_create_agent_persists_and_lists`：断言 `status` `enabled`→`disabled`。
  - `tests/integration/test_agent_console_api.py::test_disable_then_enable`：enable 前先 `placement_store.pin_agent` 绑定 node（否则守卫 409）。
  - `tests/unit/test_coverage_admin_connector_handlers.py`：直接调 `enable_agent`，需 monkeypatch `agent_console_api.get_agent_placement` 返回非 None。
  这些是契约变更的必要伴随修改，更新后应转绿。
- **N+1**：D2 已规避，列表固定 3 次查询。
- **运行态陈旧**：platform 只读投影，`reported_at` 可能滞后于真实进程；透出 `reported_at` 由前端判断，不在本 change 内做心跳超时染色（留待后续）。
- **seam 未接线时静默退化**：默认返回 `None`/`[]`，控制台只显示期望态。`server.py` 接线后恢复双态；接线本身有 integration 覆盖。
