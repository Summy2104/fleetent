# Tasks

> C1：数据基座。TDD 每步先窄命令见红→实现见绿。**DB/schema/CRUD 测试一律归 `tests/integration/`**（unit 边界禁真实 DB/Alembic）。迁移号 apply 时取当时 head+1（现 head 095），不写死。

## 1. 迁移：nodes + agent_placements

- [ ] 1.1 写 integration 测试：迁移后 `nodes`、`agent_placements` 两表存在，列与约束正确（PK、FK CASCADE/RESTRICT、唯一约束）；`uv run pytest tests/integration/<f>::<t> -x -q` 见红
- [ ] 1.2 写 Alembic 迁移 `<next>_add_node_registry.py`（`revision` 取当时 head+1、`down_revision` 指当时 head）：建 `nodes`(id TEXT PK, name, key_hash, labels JSON, registered_at, last_seen_at NULL, created_at, updated_at) + `agent_placements`(agent_id INTEGER PK→agents.id CASCADE, node_id TEXT→nodes.id RESTRICT, pinned_at, pinned_by, updated_at)；同一命令见绿
- [ ] 1.3 收尾跑 integration 该文件，确认表/约束断言全绿

## 2. node 注册表 store + 身份解析

- [ ] 2.1 integration 测试：register 生成 node + 返回一次性 `ma-` key、仅哈希持久化；重复 node-id 冲突；`resolve_node_key` 有效→node 身份、无效→None；list；deregister 空闲 node 成功、占用 node 拒绝。见红
- [ ] 2.2 实现 `platform/node_management/node_store.py`：register/list/deregister/resolve_node_key（沿用 `api_key_store._hash`，named params `:x` 占位风格，走统一 `db.py` 边界）。见绿
- [ ] 2.3 收尾跑该 integration 文件全绿

## 3. placement store

- [ ] 3.1 integration 测试：pin(agent,node) 写入；重新 pin 覆盖仍 1:1；pin 不存在 agent/node 拒绝；unpin 删除；按 node 列归属 agent；按 agent 查 node。见红
- [ ] 3.2 实现 `platform/node_management/placement_store.py`：pin/unpin/list_by_node/get_for_agent。见绿
- [ ] 3.3 收尾跑该 integration 文件全绿

## 4. fleetent-admin 运维入口

- [ ] 4.1 测试：`fleetent-admin node register/list/deregister` 与 `pin/unpin` 子命令解析 + 调对应 store（CLI 解析可 unit；触 DB 的端到端走 integration）。见红
- [ ] 4.2 实现 `platform/admin_cli/nodes.py`（`register.py` 风格 `register(subparsers)`），并在 `admin_cli/main.py` 挂载；register 打印一次性 key。见绿
- [ ] 4.3 收尾跑相关测试全绿

## 5. 收尾验证

- [ ] 5.1 `make test-pr` 全绿（unit + 层边界 + changed-vs-main ruff）
- [ ] 5.2 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线，无新增失败）
- [ ] 5.3 边界核验：`node_management` 不被 agent runtime import；表仅 Alembic 维护（store 内无 `_init_db()` 建这两表）；`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过
- [ ] 5.4 `openspec validate agent-node-registry` 通过
