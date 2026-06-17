# Tasks

> C4：secret 分区下发 + env 注入。TDD 每步先窄命令见红→见绿。platform 侧测试触 DB/凭证库归 `tests/integration/`；node 侧注入/缓存逻辑用 mock 可 unit。**无管理库迁移**。**铁律：secret 绝不落盘、绝不入日志、绝不混进 config。**

## 1. platform 侧：desired-state 附 per-agent secrets

- [x] 1.1 integration 测试：`GET /nodes/{id}/desired-state` 每 agent 含独立 `secrets`（源自 `credential_slots.list_slots`+`secret_store.get_decrypted`，仅 `status=="set"` 的槽）；`config` 仍非密（不含 secret 值）；只含本 node enabled agent 的 secret，不含他 node。见红
- [x] 1.2 在 `node_desired_state_api.get_desired_state` 每 agent 条目加 `secrets`（复用 credential_slots+secret_store，与 materialize 写 .env 同源；保持 config 经 `_strip_secret_plumbing` 不变）。见绿
- [x] 1.3 收尾跑全绿

## 2. node 侧：provider 解析 secrets + 缓存剥除

- [x] 2.1 测试：`DesiredAgent` 解析 `secrets` 字段；写磁盘缓存时**剥掉 secret**（缓存只含 config）；读缓存得到的 agent secrets 为空。见红
- [x] 2.2 `node/provider.py`：`DesiredAgent` 加 `secrets` 字段，`_desired_state_from_payload` 解析；`_write_cache` 序列化前剥 secret。见绿
- [x] 2.3 收尾跑全绿

## 3. node 侧：backend.spawn 注入 env

- [x] 3.1 测试(mock subprocess)：`spawn(name, env=secrets)` 把 secret 经 `Popen(env=...)` 传入（含 `os.environ` 合并）；secret 不写任何文件。见红
- [x] 3.2 `node/backend.py`：`BaseProcessBackend.spawn` 与 `LocalBackend.spawn` 加 `env` 参数，`Popen(env={**os.environ, **secrets})`。见绿
- [x] 3.3 收尾跑全绿

## 4. node 侧：reconcile 串接 secret + 降级

- [x] 4.1 测试：reconcile 把 `desired.secrets` 传给 `spawn`；config-hash 重启后 spawn 重新带当前 secret；platform-down 回落缓存时——在跑 agent 维持(不重启不丢 secret)、缺 secret 的新启动**推迟**(不无 secret 强启)并记录。见红
- [x] 4.2 `node/reconcile.py`：spawn 调用传 `desired.secrets`；重启路径重新带 secret；降级分支按"维持/推迟"处理。见绿
- [x] 4.3 收尾跑全绿

## 5. secret 不入日志

- [x] 5.1 测试：拉取/注入/降级路径日志不含 secret 明文（至多 env 名/长度）。见红
- [x] 5.2 审查并修正相关日志点。见绿

## 6. 收尾验证

- [x] 6.1 `make test-pr` 全绿
- [x] 6.2 `make test-unit-ci`（覆盖率关 `--fail-under=76`）通过
- [x] 6.3 `uv run pytest tests/integration -q`（对照 main 基线无新增失败）
- [x] 6.4 边界：`node/` 仍零 platform/runtime 内部 import（`check_module_boundaries.py`）
- [x] 6.5 `openspec validate node-secret-delivery` 通过
- [x] 6.6 端到端抽查（手动或 e2e）：用一个需 secret 的最小 agent，确认 node 拉起后 agent 拿到注入的 env、能连外部；agent home 磁盘无 secret、缓存文件无 secret
