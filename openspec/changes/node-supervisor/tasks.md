# Tasks

> C3：node supervisor（新顶层 `node/` 包 + `fleetent-node` 二进制）。TDD 每步先窄命令见红→见绿。node 逻辑用 mock HTTP(respx)+mock subprocess 可 unit；真实 node↔platform↔spawn 端到端归 integration/e2e。**边界铁律**：`node/` 不 import platform、不 import runtime 内部（仅 HTTP + subprocess）。本 change 无管理库迁移。

## 1. runtime CLI 加 `fleetent agent stop`

- [ ] 1.1 测试：`fleetent agent stop <id>` 对在跑进程触发 drain（复用 `_stop_running`）；无 pid/已退出时幂等成功（可 unit mock `_stop_running`，端到端归 integration）。见红
- [ ] 1.2 在 `__main__.py` 加 `agent stop` 分支，resolve_home + 调 `agent_app._stop_running`。见绿
- [ ] 1.3 收尾跑相关测试全绿

## 2. node 包骨架 + 配置 + 二进制

- [ ] 2.1 测试：配置加载（platform 基址/node-id/service key/FLEETENT_HOME/间隔）；缺必需项报错退出。见红
- [ ] 2.2 建 `src/fleetent/node/`（`__init__.py`、`config.py`），`pyproject.toml` 加 `fleetent-node` entry point。见绿
- [ ] 2.3 收尾跑全绿

## 3. desired-state provider（platform-api）+ 本地缓存

- [ ] 3.1 测试(respx mock platform)：拉取并解析 `{node_id, agents:[{agent_id,name,config}]}`；带 `Authorization: Bearer <key>`；成功后写缓存；platform 不可达→回落缓存；缓存缺失→空集（不动现状）。见红
- [ ] 3.2 实现 provider 接口 + platform-api 实现 + 本地缓存读写。见绿
- [ ] 3.3 收尾跑全绿

## 4. 进程后端：接口 + local

- [ ] 4.1 测试(mock subprocess + 临时 home/PID 文件)：spawn 调 `fleetent agent run <key>`；stop 调 `fleetent agent stop <key>`；is_alive 读 `.fleetent.pid`+os.kill，stale PID 判死。见红
- [ ] 4.2 实现 `BaseProcessBackend` + `LocalBackend`。见绿
- [ ] 4.3 收尾跑全绿

## 5. reconcile + config-hash 漂移 + 上报

- [ ] 5.1 测试：期望∧未跑→spawn(先写 home)；在跑∧不在期望→stop；守护重启 re-adopt(PID 活则不重拉)；崩溃(PID 死)→重拉；config-hash 变→优雅停+重拉、不变→不动；每轮 POST status 上报；上报失败不影响本地。见红
- [ ] 5.2 实现 reconcile（实际态取 PID 探活，非内存）+ config-hash 记录/比对 + 上报；**对齐 home key 约定**（核对 runtime `resolve_home` 用 agent_id 还是 name，与写 home 一致）。见绿
- [ ] 5.3 收尾跑全绿

## 6. 守护主循环 + 二进制可跑

- [ ] 6.1 测试：`fleetent-node` 主循环按间隔 拉取→reconcile→上报；有效配置进入循环、无效退出。见红
- [ ] 6.2 实现主循环入口（`node/app.py`），wire provider/backend/reconcile。见绿
- [ ] 6.3 收尾跑全绿

## 7. 边界 + 收尾验证

- [ ] 7.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认 `node/` 不 import `fleetent.platform.*` 与 runtime 内部（仅 HTTP + subprocess）——若护栏未覆盖新包，补一条护栏断言
- [ ] 7.2 `make test-pr` 全绿
- [ ] 7.3 `make test-unit-ci`（覆盖率关 `--fail-under=76`）通过
- [ ] 7.4 `uv run pytest tests/integration -q`（对照 main 基线无新增失败）
- [ ] 7.5 `openspec validate node-supervisor` 通过
- [ ] 7.6 （无管理库迁移；如有则 merge 后 `uv run alembic -c alembic.ini heads` 确认单 head）
