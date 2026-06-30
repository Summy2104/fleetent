## 1. 管理库：nodes 表加 forward_host 列（Alembic）

- [x] 1.1 写测试（integration）：跑 Alembic `upgrade head` 后，`nodes` 表含 `forward_host` 列且为 nullable、既有行该列为 NULL；`downgrade` 后该列消失（若提供 downgrade）。先见红
- [x] 1.2 实现：新增 Alembic 迁移给 `nodes` 加 `forward_host TEXT`（nullable，默认 NULL）；令 1.1 见绿
- [x] 1.3 跑受影响层（integration migration/schema）确认无新增失败

## 2. platform：node_store 读写 forward_host

- [x] 2.1 写测试（integration）：`node_store._COLS` 含 `forward_host`；`register_node` 后 `get_forward_host` 返回 None；`set_forward_host(node_id, "10.0.0.5")` 后 `get_forward_host` 返回 `"10.0.0.5"`、`get_node` 行含该值。先见红
- [x] 2.2 写测试（integration）：`set_forward_host` 对不存在 node 不抛、不误插（UPDATE 命中 0 行）；重复 `set_forward_host` 覆盖为最新值。先见红
- [x] 2.3 实现：`_COLS` 加 `forward_host`；新增 `set_forward_host`（named-param UPDATE，刷新 `updated_at`）与 `get_forward_host`；确认 `register_node` INSERT 不写该列（保持 NULL）。令 2.1–2.2 见绿

## 3. platform：status 心跳接收并持久化 forward_host

- [x] 3.1 写测试（integration）：`NodeStatusBody` 接受缺省 `forward_host`（旧 payload 不带也能解析）。先见红
- [x] 3.2 写测试（integration）：`POST /nodes/{id}/status` body 带 `forward_host` → 落库（`get_forward_host` 返回该值）；不带 `forward_host` → 不改动既有值（不清空）。先见红
- [x] 3.3 实现：`NodeStatusBody` 加 `forward_host: str | None = None`；`post_node_status` 在 `touch_last_seen` 后，`body.forward_host` 非空时调 `node_store.set_forward_host`。令 3.1–3.2 见绿

## 4. platform：agent_transport 转发寻址优先级

- [x] 4.1 写测试（unit）：给定某 node `get_forward_host` 返回 `10.38.8.143`（mock node_store）→ `DirectHttpAgentTransport.chat` 拨号 URL host 为 `10.38.8.143:8786`（mock httpx，断言 request.url）。先见红
- [x] 4.2 写测试（unit）：`get_forward_host` 返回 None 且未设 override → URL 回落 `{node_id}.internal:8786`；设 `FLEETENT_FORWARDER_HOST_OVERRIDE` 且 `get_forward_host` None → 用 override；`get_forward_host` 有值且同时设 override → 用上报地址（上报优先于 override）。先见红
- [x] 4.3 写测试（unit）：WS 路径 `ws()` 同样优先用 `get_forward_host`（`ws://10.38.8.143:8786`），回落同 chat。先见红
- [x] 4.4 实现：`agent_transport` 内新增 host 解析助手（`node_store.get_forward_host(node_id)` 有值则拼 URL，否则回落 `forwarder_base_url`/`forwarder_ws_url`）；`chat` 与 `ws` 改用之；`forwarder_contract.py` 不改。令 4.1–4.3 见绿
- [x] 4.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过（确认 `agent_transport` 读 `node_store` 合规、`node/` 未引入 DB、无 node→platform import）

## 5. node：advertise host 配置 + 心跳上报

- [x] 5.1 写测试（unit/node）：`NodeConfig` 从 `FLEETENT_NODE_ADVERTISE_HOST=10.38.8.143` 载入 `advertise_host == "10.38.8.143"`；未设时为 None。先见红
- [x] 5.2 写测试（unit/node）：`reconcile._post_status` 在 `advertise_host` 非空时 payload 含 `forward_host`（mock httpx，断言 json）；为 None 时 payload 不含该键。先见红
- [x] 5.3 实现：`node/config.py` `NodeConfig` 加 `advertise_host` 字段并从环境读取；`reconcile._post_status` 条件加 `forward_host`。令 5.1–5.2 见绿

## 6. 文档与部署

- [x] 6.1 AGENTS.md / 相关 node 部署文档（`node.env.example`、`docs/operations/pilot-*`）补 `FLEETENT_NODE_ADVERTISE_HOST` 说明与转发寻址优先级（非代码产物，人工确认后提交）

## 7. 收尾与门禁

- [x] 7.1 `make test-pr` 全绿
- [x] 7.2 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 7.3 端到端验证：生产/本机给 node 配 `FLEETENT_NODE_ADVERTISE_HOST=127.0.0.1`，重装重启后 `POST /admin/agents/dev/chat` 不再 500、能正常聊天
