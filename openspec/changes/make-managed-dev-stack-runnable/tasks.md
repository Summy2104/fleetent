## 1. dev master key 助手（item 1）

- [x] 1.1 **测试（红）**：新增 `tests/unit/test_dev_secret_key.py`，对
  `scripts/dev_secret_key.py::ensure_dev_secret_key(home)` 断言：(a) 首次调用在 `<home>/.dev_secret_key`
  生成一个**合法 Fernet key**（可被 `cryptography.fernet.Fernet(key)` 接受）；(b) 幂等——二次调用
  返回与首次**相同**的 key、不覆盖文件。用 `tmp_path` 作 home（纯文件 IO，归 unit）。先跑见红
  （助手尚不存在）。
- [x] 1.2 **实现（绿）**：写 `scripts/dev_secret_key.py`：`ensure_dev_secret_key(home)` 文件存在则读、
  否则 `Fernet.generate_key()` 写入并返回；`__main__` 入口打印 key（供 Makefile `$(shell ...)` 取用）。
  跑 1.1 见绿。
- [x] 1.3 Makefile 接线：`dev-bootstrap` 调用助手确保 key 存在；`DEV_TARGETS` export
  `FLEETENT_SECRET_KEY`（从 `<FLEETENT_HOME>/.dev_secret_key` 读）；`.dev_secret_key` 加入
  `.gitignore`。（Makefile wiring 无单测，靠 task 3.3 live 复跑实证。）

## 2. register 不吞 key 持久化失败（item 2）

- [x] 2.1 **测试（红）**：在 `tests/integration/test_node_store.py` 新增用例：当 service key 的
  secret 持久化失败时（patch `secret_store.set` 抛异常，或不提供 `FLEETENT_SECRET_KEY` 触发
  `SecretKeyError`），`register_node` SHALL 抛出可诊断错误、且不在 `nodes` 表留下记录 / 不返回
  明文。先在当前代码跑：**必须见红**（现状是 suppress 吞掉、register 假成功）。
- [x] 2.2 **实现（绿）**：改 `src/fleetent/platform/node_management/node_store.py` 的
  `register_node`：去掉 `with suppress(Exception)` 包裹的 `secret_store.set`；改为捕获 → `logger.error`
  明确信息（指明缺 master key / secret 后端问题）+ `raise`，使 register 整体失败。确保失败时不
  残留半成品 node（如先 set 再 insert，或失败后清理）。跑 2.1 见绿。
- [x] 2.3 核对既有 register 用例（`tests/integration/test_node_store.py` 正常路径、
  `tests/unit/test_node_admin_cli.py`、`test_node_admin_api.py`）：master key 就绪的正常登记仍绿；
  如有依赖"register 永不抛"的用例需按新语义更新（保持其原意）。

## 3. forwarder 地址 override（item 3）+ 收尾

- [ ] 3.1 **测试（红）**：在 `tests/unit/test_platform_agent_gateway.py` 新增用例：
  `forwarder_contract.forwarder_base_url(node_id)` / `forwarder_ws_url(node_id)` 在设置
  `FLEETENT_FORWARDER_HOST_OVERRIDE` 时用 override host、未设时回落 `<node_id>.internal`
  默认契约（端口/scheme 不变）。用 monkeypatch.setenv。先跑见红。
- [ ] 3.2 **实现（绿）**：改 `src/fleetent/node/forwarder_contract.py`：两函数 honor
  `FLEETENT_FORWARDER_HOST_OVERRIDE`（设则用、否则 `<node_id>.internal`）。Makefile dev 目标
  export `FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1`。跑 3.1 见绿。
- [ ] 3.3 **收尾**：`make test-pr` 全绿（对照 main 基线无新增失败）+ 相关测试
  `uv run pytest tests/unit/test_dev_secret_key.py tests/integration/test_node_store.py tests/unit/test_platform_agent_gateway.py -q` 无新增失败；跑覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [ ] 3.4 **（建议）live 实证**：隔离 dev home 走 `make dev-bootstrap → platform → node-provision →
  node`，确认 register 落库 key、`get_node_service_key` 非空、平台经 forwarder（override 到
  127.0.0.1）拨通（配合 fix-streaming 落地后应能拿到完整流）。
