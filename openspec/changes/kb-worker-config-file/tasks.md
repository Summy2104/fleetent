## 前置条件

**`kb-worker` 已落地 main**(`fleetent kb-worker` 进程 + 消费循环)。apply 前确认。

## 1. worker 从 .env 加载自身配置

- [ ] 1.1 [测试] `tests/unit/test_kb_worker_config.py`(tmp_path + monkeypatch FLEETENT_HOME,纯配置解析、无 DB):
  - `test_loads_kb_worker_env_file`:写 `<home>/kb-worker/.env`、清进程 env → 取文件值
  - `test_process_env_overrides`:都设 → 取进程 env(override=False)
  - `test_missing_file_falls_back_to_process_env`:无文件 → 用进程 env
  → 红
- [ ] 1.2 [实现] worker 配置加载:解析 `FLEETENT_HOME` → `load_dotenv(home/"kb-worker"/".env", override=False)` → 读队列/底座/embedder/Vault 接入(照抄 agent_app .env 范式)
- [ ] 1.3 [验证] `uv run pytest tests/unit/test_kb_worker_config.py -x -q` → 绿

## 2. 配置模板

- [ ] 2.1 [实现] 新增 `config/kb-worker.env.example`:队列连接 / 底座连接 / embedder / Vault 接入;注释:复制到 `$FLEETENT_HOME/kb-worker/.env`、权限 0600、`FLEETENT_HOME` 须进程 env、**connector 配置不在此(控制面 per-job 下发)**
- [ ] 2.2 [验证] `.gitignore` 覆盖实际 `.env`(只提交 `.example`)

## 3. 收尾验证

- [ ] 3.1 [验证] `make test-pr` 全绿;`make test-unit-ci` 覆盖率 ≥ 76%
- [ ] 3.2 [验证] `openspec validate kb-worker-config-file`;archive 后 `opsx:verify` 确认 kb-ingest-worker spec 与实现一致
