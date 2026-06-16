# Tasks

> C2：承重契约。TDD 每步先窄命令见红→实现见绿。HTTP/DB/schema 测试归 `tests/integration/`（FastAPI TestClient + 真实 DB）。迁移号 apply 时取当时 head+1（C1 后预期 097，**勿写死**），merge 后自检单 head。配置载荷**只下发非密**（secret 留 C4）。

## 1. 迁移：node_agent_status（实际态投影表）

- [ ] 1.1 integration 测试：迁移后 `node_agent_status` 存在，列/约束正确（agent_id PK→agents CASCADE、node_id→nodes CASCADE）。见红
- [ ] 1.2 Alembic 迁移 `<next>_add_node_agent_status.py`（`revision` 取当时 head+1、`down_revision` 指当时 head）。见绿
- [ ] 1.3 收尾跑该文件全绿

## 2. node 鉴权 seam（resolve_node_key + URL 自限）

- [ ] 2.1 integration 测试：有效 node key→通过；无效→401；node A 访问 node B 的 `{id}`→403；user 的 `ma-` key 不能当 node key（反之亦然）。见红
- [ ] 2.2 实现 node 鉴权依赖（仿 server 既有 `_authenticate`/resolver 注入模式），用 `node_store.resolve_node_key` + 校验 URL `{id}` 等于解析出的 node-id。见绿
- [ ] 2.3 收尾跑全绿

## 3. desired-state 配置载荷序列化（非密）

- [ ] 3.1 测试：从 store 产出的 AgentFile 序列化为可下发 dict/yaml，含非密字段、**剔除任何 secret 字段**（解析/序列化纯逻辑可 unit；触 store 的走 integration）。见红
- [ ] 3.2 实现序列化 helper（复用 `materialize.agent_file_from_store`，不改其写盘路径）。见绿
- [ ] 3.3 收尾跑全绿

## 4. GET /nodes/{id}/desired-state

- [ ] 4.1 integration 测试：只返回本 node（`placement_store.list_by_node`）且 `status==enabled` 的 agent（disabled/archived 不出现）；每 agent 附配置载荷；空归属返回空集；鉴权/自限生效。见红
- [ ] 4.2 实现端点：鉴权(task2) → list_by_node → 过滤 enabled(`agent_admin_store.get_state`) → 附载荷(task3)。见绿
- [ ] 4.3 收尾跑全绿

## 5. POST /nodes/{id}/status（实际态 + 心跳）

- [ ] 5.1 integration 测试：上报刷新 `nodes.last_seen_at`；per-agent 实际态写 `node_agent_status` 且可查询；鉴权/自限生效。见红
- [ ] 5.2 实现端点 + `node_store` 加 `touch_last_seen` / 实际态 upsert（named params、走 `db.py` 边界）。见绿
- [ ] 5.3 收尾跑全绿

## 6. 路由挂载 + 边界

- [ ] 6.1 在 `server.py` 挂载 node 端点 router；确认仅 platform 侧、不被 agent runtime import
- [ ] 6.2 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过

## 7. 收尾验证

- [ ] 7.1 `make test-pr` 全绿
- [ ] 7.2 `make test-unit-ci`（CI 覆盖率关 `--fail-under=76`）通过——新增 integration-only 代码勿拖垮 unit 覆盖
- [ ] 7.3 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线，无新增失败）
- [ ] 7.4 `openspec validate node-desired-state-api` 通过
- [ ] 7.5 merge 后 `uv run alembic -c alembic.ini heads` 确认**单一 head**（撞号则改号重链）
