## 1. node 从 .env 加载配置

- [x] 1.1 [测试] `tests/unit/test_node_config.py` 新增(用 `tmp_path` + monkeypatch `FLEETENT_HOME`,纯配置解析、无 DB):
  - `test_load_config_reads_node_env_file`:写 `<home>/node/.env` 含三必需变量、清掉进程 env → `load_config()` 取到文件值
  - `test_process_env_overrides_node_env`:文件与进程 env 都设 → 取进程 env 值(override=False)
  - `test_missing_node_env_falls_back_to_process_env`:无文件、进程 env 有值 → 成功
  - `test_missing_required_still_raises`:无文件、进程 env 也缺 → `ConfigError`
  → 运行必须红
- [x] 1.2 [实现] `node/config.py::load_config()`:解析 `home_dir` 后、读 `FLEETENT_NODE_*` 前,`load_dotenv(home_dir / "node" / ".env", override=False)`(文件存在才加载;照抄 `agent_app.py:381-385` 范式)。`FLEETENT_HOME` 仍只从进程 env 解析。
- [x] 1.3 [验证] `uv run pytest tests/unit/test_node_config.py -x -q` → 全绿

## 2. 配置模板

- [x] 2.1 [实现] 新增 `config/node.env.example`:含 `FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` / `FLEETENT_NODE_INTERVAL_SECONDS`,注释说明:复制到 `$FLEETENT_HOME/node/.env`、建议权限 0600、`FLEETENT_HOME` 须经进程环境而非本文件、service key 来自 `fleetent admin node register`
- [x] 2.2 [验证] 确认 `.gitignore` 覆盖实际 `.env`(不提交真实 secret;只提交 `.example`)

## 3. 收尾验证

- [x] 3.1 [验证] `make test-pr` → 全绿
- [x] 3.2 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [x] 3.3 [验证] `openspec validate node-config-file`;archive 后 `opsx:verify` 确认 node-supervisor spec 与实现一致
