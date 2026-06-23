# tasks — agent-dual-state-gating

> 每组「写测试（先红）」必须在「实现（绿）」之前；每步用最窄命令见红/见绿。
> platform 用 integration（真实 DB），纯 seam 行为可用 unit；前端用 Vitest。

## 1. node/placement 只读读函数（integration，TDD）

- [ ] 1.1 写测试（先红）：`tests/integration/test_node_store.py`（或既有 node_store 测试文件）——
  `node_store.get_agent_status(agent_id)`：`upsert_agent_status` 写入后能按 agent_id 读回 `phase/pid/health/node_id/reported_at`；无行返回 `None`。
  `node_store.list_agent_status()`：返回所有 agent 的状态行列表；空表返回 `[]`。
  `placement_store.list_placements()`：`pin_agent` 后返回所有 placement 行；空表返回 `[]`。先跑见红。
- [ ] 1.2 实现（绿）：在 `node_store.py` 新增只读 `get_agent_status` / `list_agent_status`（复用 `_STATUS_COLS`，不动 `upsert_agent_status`）；在 `placement_store.py` 新增只读 `list_placements`（复用 `_COLS`）。同命令见绿。

## 2. console 查询合并双态（integration，TDD）

- [ ] 2.1 写测试（先红）：`tests/integration/test_agent_console_api.py`——
  列表 `GET /admin/agents`：seed `node_agent_status`(running/pid/health) + `agent_placements`(node)，断言对应 agent 行含 `runtime={phase,health,pid,node_id,reported_at}` 与 `placement={node_id,...}`；未上报/未绑定的 agent `runtime`/`placement` 为 `null`；既有字段（status/provenance/agent_name）不变。
  详情 `GET /admin/agents/{name}`：同样断言含 `runtime`/`placement`；未绑定时 `placement` 为 `null`。先跑见红。
- [ ] 2.2 实现（绿）：在 `agent_console_api.py` 新增模块级 seam `get_agent_runtime`/`get_agent_placement`（单条，默认 `None`）+ `list_agent_runtimes`/`list_agent_placements`（批量，默认 `[]`）；列表批量 join（按 `agent_id` 构 map，避免 N+1），详情用单条 seam；新增 `runtime`/`placement` 字段，不破坏既有字段。测试 helper 把新 seam monkeypatch 到真实 `node_store`/`placement_store`。同命令见绿。

## 3. 默认 disabled（integration，TDD）

- [ ] 3.1 写测试（先红）：`tests/integration/test_agent_console_api.py`——
  `POST /admin/agents` 后 `agent_admin_store.get_state(id)["status"] == "disabled"`；
  `POST /admin/agents/{name}/clone` 后克隆体 `status == "disabled"`。先跑见红。
- [ ] 3.2 实现（绿）：`create_agent`（L353）与 `clone_agent`（L495）由 `agent_admin_store.enable` 改 `agent_admin_store.disable`。
  同步更新既有 `test_create_agent_persists_and_lists`（断言 `status` `enabled`→`disabled`）。同命令见绿。

## 4. enable 守卫（integration + unit，TDD）

- [ ] 4.1 写测试（先红）：`tests/integration/test_agent_console_api.py`——
  未绑定 node 时 `POST /admin/agents/{name}/enable` 返回 409 且 body detail 含 `agent not bound to a node`，状态仍 `disabled`、无 `agent.enable` 审计；
  先 `placement_store.pin_agent` 绑定 node 后 enable 返回 200、状态 `enabled`；
  `disable` 在未绑定时仍 200（不守卫）。先跑见红。
- [ ] 4.2 实现（绿）：`enable_agent` 在 `_require_admin` 后、`enable` 前调 `get_agent_placement(agent_id)`，为 `None` 抛 `HTTPException(409, "agent not bound to a node")`。
  同步更新既有 `test_disable_then_enable`（enable 前先 `pin_agent`）与 `tests/unit/test_coverage_admin_connector_handlers.py`（monkeypatch `agent_console_api.get_agent_placement` 返回非 None）。同命令见绿。

## 5. server.py seam 接线（integration，TDD）

- [ ] 5.1 写测试（先红）：断言 `server.wire_agent_store_seams()` 后 `agent_console_api.get_agent_runtime` / `get_agent_placement` / `list_agent_runtimes` / `list_agent_placements` 分别为 `node_store.get_agent_status` / `placement_store.get_for_agent` / `node_store.list_agent_status` / `placement_store.list_placements`。先跑见红。
- [ ] 5.2 实现（绿）：在 `wire_agent_store_seams` 中接线四个新 seam。同命令见绿。

## 6. 前端双态 + Enable gating（Vitest，TDD）

- [ ] 6.1 写测试（先红）：`frontend/src/features/agents/`——
  `api.test.tsx`：`AgentListItem`/`AgentDetail` 携带 `runtime`/`placement`（类型 + 解析）。
  `page.test.tsx`：MSW 返回带 `runtime`(running, node) + `placement`(node) 的 agent，断言卡片展示运行态（running/health/所在 node）；返回 `status=disabled` 且 `placement=null` 的 agent，断言「Enable」按钮 `disabled` 且有原因提示；`placement` 非空时 Enable 可点。先跑见红。
- [ ] 6.2 实现（绿）：`api.ts` 给 `AgentListItem`/`AgentDetail` 增加 `runtime?`/`placement?` 类型；`page.tsx` `formatStatus`/卡片展示运行态，Enable 按钮在 `status==='disabled' && !placement` 时 `disabled` + 提示。同命令见绿。

## 7. 收尾门禁

- [ ] 7.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [ ] 7.2 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败。
- [ ] 7.3 改动文件 `uv run ruff check`/`ruff format` + `uv run mypy src` 干净。
- [ ] 7.4 前端 `yarn vitest run src/features/agents` 通过。
- [ ] 7.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新违规。

## 8. spec 文档对齐（archive 时同步）

- [ ] 8.1 `opsx:archive` 同步：`agent-admin-api`（create disabled + enable 守卫 + 双态查询）、`agent-lifecycle-toggle`（enable 需绑定 node + 起始 disabled）、`agent-admin-ui`（双态展示 + Enable gating）delta 落到 `openspec/specs/`。
